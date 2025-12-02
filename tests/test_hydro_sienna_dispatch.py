#!/usr/bin/env python3
"""Test hydro dispatch in Sienna to verify time series constraints are applied."""

import pypsa
import pandas as pd
import numpy as np
from pathlib import Path
import subprocess
import json
from r2x.api import System
from infrasys import TimeSeriesStorageType
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization import create_default_mapping
from r2x_pypsa.serialization.to_sienna import infrasys_to_psy
from loguru import logger

def create_test_network():
    """Create a simple PyPSA network with hydro that has constrained time series."""
    network = pypsa.Network()
    
    # Add a bus
    network.add("Bus", "bus1", v_nom=230)
    
    # Add a hydro generator with LOW capacity factor time series
    p_nom = 100.0  # 100 MW nameplate
    network.add(
        "Generator",
        "hydro1",
        bus="bus1",
        carrier="hydro",
        p_nom=p_nom,
        marginal_cost=10.0,
        p_max_pu=1.0,
    )
    
    # Add a thermal generator (higher cost, backup)
    network.add(
        "Generator",
        "thermal1",
        bus="bus1",
        carrier="gas",
        p_nom=200.0,
        marginal_cost=50.0,
    )
    
    # Create time series with CONSTRAINED capacity factors (0.2 = 20% max)
    snapshots = pd.date_range("2030-01-01", periods=168, freq="h")
    network.set_snapshots(snapshots)
    
    # Set p_max_pu to 0.2 (20% of nameplate = 20 MW max)
    capacity_factors = np.full(168, 0.2)  # Constant 20% capacity factor
    
    network.generators_t.p_max_pu = pd.DataFrame(
        {"hydro1": capacity_factors},
        index=snapshots
    )
    
    # Add a load that requires more than hydro can provide
    network.add("Load", "load1", bus="bus1", p_set=30.0)  # 30 MW load
    
    return network


def test_hydro_sienna_dispatch():
    """Test that Sienna respects hydro time series constraints."""
    print("=" * 80)
    print("TEST: Hydro Dispatch in Sienna")
    print("=" * 80)
    
    # Create network
    print("\n1. Creating test network...")
    network = create_test_network()
    
    hydro_gen = network.generators.loc["hydro1"]
    p_nom = hydro_gen.p_nom
    p_max_pu_ts = network.generators_t.p_max_pu["hydro1"]
    
    print(f"   Hydro: {p_nom} MW nameplate")
    print(f"   p_max_pu time series: {p_max_pu_ts.iloc[0]:.1%} (constant)")
    print(f"   Max allowed dispatch: {p_max_pu_ts.iloc[0] * p_nom:.1f} MW")
    print(f"   Load: {network.loads.loc['load1', 'p_set']} MW")
    
    # Optimize PyPSA
    print("\n2. Optimizing PyPSA...")
    network.optimize(solver_name='gurobi')
    
    if network.objective is None:
        print("   ✗ PyPSA optimization failed")
        return False
    
    pypsa_dispatch = network.generators_t.p["hydro1"]
    print(f"   ✓ PyPSA optimization successful")
    print(f"   PyPSA hydro dispatch: {pypsa_dispatch.sum():.2f} MWh total")
    print(f"   PyPSA hydro average: {pypsa_dispatch.mean():.2f} MW")
    print(f"   PyPSA hydro max: {pypsa_dispatch.max():.2f} MW")
    print(f"   Expected max: {p_max_pu_ts.iloc[0] * p_nom:.2f} MW")
    
    if pypsa_dispatch.max() > p_max_pu_ts.iloc[0] * p_nom + 1e-6:
        print(f"   ✗ PyPSA violates constraint!")
        return False
    
    # Convert to PowerSystems
    print("\n3. Converting to PowerSystems...")
    parser = PypsaParser(network=network)
    pypsa_system = parser.build_system()
    mapping = create_default_mapping()
    psy_system = System(
        name="Test PSY",
        auto_add_composed_components=True,
        time_series_storage_type=TimeSeriesStorageType.HDF5
    )
    
    for component in pypsa_system._component_mgr.iter_all():
        try:
            pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
        except Exception as e:
            logger.warning(f"Failed to convert {component.name}: {e}")
            continue
    
    # Serialize
    output_dir = Path("tests/test_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "test_hydro_sienna.json"
    
    print(f"\n4. Serializing to Sienna format...")
    infrasys_to_psy(psy_system, filename=output_file)
    print(f"   ✓ Serialized to: {output_file}")
    
    # Run Sienna optimization
    print(f"\n5. Running Sienna optimization...")
    objective_file = output_dir / "test_hydro_sienna_objective.txt"
    
    julia_cmd = [
        "julia",
        "--project=tests",
        "tests/run_sienna_ed.jl",
        str(output_file),
        str(objective_file),
    ]
    
    try:
        result = subprocess.run(
            julia_cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        if result.returncode != 0:
            print(f"   ✗ Sienna optimization failed:")
            print(f"   {result.stderr}")
            return False
        
        print(f"   ✓ Sienna optimization successful")
        
        # Read Sienna dispatch
        dispatch_file = output_dir / "sienna_dispatch.csv"
        if dispatch_file.exists():
            dispatch_df = pd.read_csv(dispatch_file)
            hydro_dispatch = dispatch_df[dispatch_df['carrier'] == 'hydro']
            
            if len(hydro_dispatch) > 0:
                sienna_total = hydro_dispatch['value'].sum()
                sienna_max = hydro_dispatch['value'].max()
                sienna_avg = hydro_dispatch['value'].mean()
                
                print(f"\n6. Comparing dispatch:")
                print(f"   PyPSA total: {pypsa_dispatch.sum():.2f} MWh")
                print(f"   Sienna total: {sienna_total:.2f} MWh")
                print(f"   PyPSA max: {pypsa_dispatch.max():.2f} MW")
                print(f"   Sienna max: {sienna_max:.2f} MW")
                print(f"   Expected max: {p_max_pu_ts.iloc[0] * p_nom:.2f} MW")
                
                # Check if Sienna respects constraint
                expected_max = p_max_pu_ts.iloc[0] * p_nom
                if sienna_max > expected_max + 1e-6:
                    print(f"\n   ✗ Sienna violates constraint!")
                    print(f"     Max allowed: {expected_max:.2f} MW")
                    print(f"     Sienna max: {sienna_max:.2f} MW")
                    print(f"     Difference: {sienna_max - expected_max:.2f} MW")
                    return False
                else:
                    print(f"\n   ✓ Sienna respects constraint!")
                    
                    # Check if totals are similar
                    diff_pct = abs(sienna_total - pypsa_dispatch.sum()) / pypsa_dispatch.sum() * 100
                    if diff_pct < 5.0:  # Allow 5% difference
                        print(f"   ✓ Dispatch totals match (diff: {diff_pct:.1f}%)")
                        return True
                    else:
                        print(f"   ⚠ Dispatch totals differ by {diff_pct:.1f}%")
                        return True  # Still pass if constraint is respected
            else:
                print(f"   ✗ No hydro dispatch found in Sienna results")
                return False
        else:
            print(f"   ✗ Dispatch file not found: {dispatch_file}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"   ✗ Sienna optimization timed out")
        return False
    except FileNotFoundError:
        print(f"   ✗ Julia not found. Install Julia and ensure it's in PATH.")
        return False
    except Exception as e:
        print(f"   ✗ Error running Sienna: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("HYDRO SIENNA DISPATCH TEST")
    print("=" * 80)
    
    passed = test_hydro_sienna_dispatch()
    
    print("\n" + "=" * 80)
    print("TEST RESULT")
    print("=" * 80)
    if passed:
        print("✓ TEST PASSED - Sienna respects hydro time series constraints")
        exit(0)
    else:
        print("✗ TEST FAILED - Sienna does not respect hydro time series constraints")
        exit(1)

