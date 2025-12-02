#!/usr/bin/env python3
"""Test hydro generator time series conversion from PyPSA to PowerSystems."""

import pypsa
import pandas as pd
import numpy as np
from pathlib import Path
from r2x.api import System
from infrasys import TimeSeriesStorageType
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization import create_default_mapping
from r2x.models import HydroDispatch
from loguru import logger

def create_test_network_with_hydro():
    """Create a simple PyPSA network with a hydro generator that has p_max_pu time series."""
    network = pypsa.Network()
    
    # Add a bus
    network.add("Bus", "bus1", v_nom=230)
    
    # Add a hydro generator with time-varying capacity factor
    p_nom = 100.0  # 100 MW nameplate
    network.add(
        "Generator",
        "hydro1",
        bus="bus1",
        carrier="hydro",
        p_nom=p_nom,
        marginal_cost=10.0,  # Need non-zero cost for optimization
        p_max_pu=1.0,  # Static value (will be overridden by time series)
    )
    
    # Add a thermal generator for comparison (higher cost)
    network.add(
        "Generator",
        "thermal1",
        bus="bus1",
        carrier="gas",
        p_nom=200.0,
        marginal_cost=50.0,  # Higher cost than hydro
    )
    
    # Create time series with varying capacity factors (0.1 to 0.8)
    snapshots = pd.date_range("2030-01-01", periods=168, freq="H")  # 1 week
    network.set_snapshots(snapshots)
    
    # Create p_max_pu time series (capacity factors)
    # Vary between 0.1 and 0.8 with some pattern
    capacity_factors = 0.1 + 0.7 * np.sin(np.arange(168) * 2 * np.pi / 24) ** 2
    capacity_factors = np.clip(capacity_factors, 0.1, 0.8)
    
    network.generators_t.p_max_pu = pd.DataFrame(
        {"hydro1": capacity_factors},
        index=snapshots
    )
    
    # Add a load
    network.add("Load", "load1", bus="bus1", p_set=50.0)  # 50 MW constant load
    
    return network


def test_hydro_timeseries_conversion():
    """Test that hydro time series is correctly converted to PowerSystems."""
    print("=" * 80)
    print("TEST: Hydro Time Series Conversion")
    print("=" * 80)
    
    # Create test network
    print("\n1. Creating test PyPSA network with hydro generator...")
    network = create_test_network_with_hydro()
    
    # Get hydro generator data
    hydro_gen = network.generators.loc["hydro1"]
    p_nom = hydro_gen.p_nom
    p_max_pu_ts = network.generators_t.p_max_pu["hydro1"]
    
    print(f"   Hydro generator: {hydro_gen.name}")
    print(f"   p_nom: {p_nom} MW")
    print(f"   p_max_pu time series range: [{p_max_pu_ts.min():.3f}, {p_max_pu_ts.max():.3f}]")
    print(f"   p_max_pu time series mean: {p_max_pu_ts.mean():.3f}")
    print(f"   Expected max dispatch range: [{p_max_pu_ts.min() * p_nom:.1f}, {p_max_pu_ts.max() * p_nom:.1f}] MW")
    print(f"   Expected average dispatch: {p_max_pu_ts.mean() * p_nom:.1f} MW")
    
    # Convert to PowerSystems
    print("\n2. Converting to PowerSystems...")
    parser = PypsaParser(network=network)
    pypsa_system = parser.build_system()
    
    mapping = create_default_mapping()
    psy_system = System(
        name="Test PSY system",
        auto_add_composed_components=True,
        time_series_storage_type=TimeSeriesStorageType.HDF5
    )
    
    # Convert components
    for component in pypsa_system._component_mgr.iter_all():
        try:
            pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
        except Exception as e:
            logger.warning(f"Failed to convert {component.name}: {e}")
            continue
    
    # Check hydro generator in PowerSystems
    print("\n3. Checking PowerSystems hydro generator...")
    try:
        hydro_psy = psy_system.get_component(HydroDispatch, "hydro1")
        print(f"   ✓ Found hydro generator: {hydro_psy.name}")
        print(f"   base_power: {hydro_psy.base_power} MW")
        print(f"   active_power_limits: min={hydro_psy.active_power_limits.min:.2f} MW, max={hydro_psy.active_power_limits.max:.2f} MW")
    except Exception as e:
        print(f"   ✗ Could not find hydro generator: {e}")
        return False
    
    # Check time series
    print("\n4. Checking time series...")
    if psy_system.has_time_series(hydro_psy, "max_active_power"):
        ts_psy = psy_system.get_time_series(hydro_psy, "max_active_power")
        print(f"   ✓ Time series found: {type(ts_psy).__name__}")
        
        # Get time series data
        if hasattr(ts_psy, 'data'):
            ts_data = ts_psy.data
            if hasattr(ts_data, 'values'):
                ts_values = ts_data.values
            elif hasattr(ts_data, '__iter__'):
                ts_values = np.array(list(ts_data))
            else:
                ts_values = np.array([ts_data])
            
            print(f"   Time series length: {len(ts_values)}")
            print(f"   Time series range: [{ts_values.min():.3f}, {ts_values.max():.3f}]")
            print(f"   Time series mean: {ts_values.mean():.3f}")
            
            # Check if it's in per-unit (0-1) or MW
            if ts_values.max() <= 1.1:  # Allow small tolerance
                print(f"   ✓ Time series is in PER-UNIT (0-1) - CORRECT for hydro")
                print(f"   Expected range after scaling: [{ts_values.min() * p_nom:.1f}, {ts_values.max() * p_nom:.1f}] MW")
                
                # Verify it matches PyPSA p_max_pu
                if len(ts_values) == len(p_max_pu_ts):
                    diff = np.abs(ts_values - p_max_pu_ts.values)
                    max_diff = diff.max()
                    if max_diff < 0.01:  # Allow small numerical differences
                        print(f"   ✓ Time series matches PyPSA p_max_pu (max diff: {max_diff:.6f})")
                        return True
                    else:
                        print(f"   ✗ Time series does NOT match PyPSA p_max_pu (max diff: {max_diff:.6f})")
                        print(f"     First 10 PyPSA: {p_max_pu_ts.iloc[:10].values}")
                        print(f"     First 10 PowerSystems: {ts_values[:10]}")
                        return False
                else:
                    print(f"   ✗ Time series length mismatch: PyPSA={len(p_max_pu_ts)}, PowerSystems={len(ts_values)}")
                    return False
            else:
                print(f"   ✗ Time series is in MW (max={ts_values.max():.2f}) - INCORRECT for hydro!")
                print(f"   Expected per-unit values (0-1), but got MW values")
                print(f"   This suggests the time series was NOT stored in per-unit")
                return False
        else:
            print(f"   ✗ Could not extract time series data")
            return False
    else:
        print(f"   ✗ No time series found for hydro generator")
        return False


def test_hydro_dispatch_after_optimization():
    """Test that hydro dispatch respects time series constraints after optimization."""
    print("\n" + "=" * 80)
    print("TEST: Hydro Dispatch After Optimization")
    print("=" * 80)
    
    # Create and optimize network
    print("\n1. Creating and optimizing PyPSA network...")
    network = create_test_network_with_hydro()
    
    # Set capital costs to zero for pure ED
    for component_type in ['Generator', 'StorageUnit', 'Store', 'Link', 'Line']:
        if component_type in network.components.keys():
            df = network.df(component_type)
            if 'capital_cost' in df.columns:
                df['capital_cost'] = 0.0
            if 'p_nom_extendable' in df.columns:
                df['p_nom_extendable'] = False
    
    # Optimize
    network.optimize(solver_name='gurobi')
    
    if network.objective is None:
        print("   ✗ Optimization failed")
        return False
    
    print(f"   ✓ Optimization successful, objective: {network.objective:,.2f}")
    
    # Check hydro dispatch
    if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
        hydro_dispatch = network.generators_t.p["hydro1"]
        p_max_pu_ts = network.generators_t.p_max_pu["hydro1"]
        p_nom = network.generators.loc["hydro1", "p_nom"]
        
        print(f"\n2. Checking hydro dispatch constraints...")
        print(f"   Total generation: {hydro_dispatch.sum():.2f} MWh")
        print(f"   Average generation: {hydro_dispatch.mean():.2f} MW")
        print(f"   Max generation: {hydro_dispatch.max():.2f} MW")
        
        # Check if dispatch respects p_max_pu constraints
        max_allowed = p_max_pu_ts * p_nom
        violations = hydro_dispatch > max_allowed + 1e-6  # Small tolerance
        
        if violations.any():
            print(f"   ✗ Dispatch violates p_max_pu constraints at {violations.sum()} timesteps")
            print(f"     Max violation: {(hydro_dispatch - max_allowed).max():.2f} MW")
            return False
        else:
            print(f"   ✓ Dispatch respects p_max_pu constraints")
            print(f"   Max allowed: {max_allowed.max():.2f} MW")
            print(f"   Actual max: {hydro_dispatch.max():.2f} MW")
            
            # Calculate what the dispatch SHOULD be (based on constraints)
            # This mimics what PyPSA does: dispatch up to p_max_pu * p_nom
            expected_total = (p_max_pu_ts * p_nom).sum()
            actual_total = hydro_dispatch.sum()
            print(f"   Expected total (if fully dispatched): {expected_total:.2f} MWh")
            print(f"   Actual total: {actual_total:.2f} MWh")
            
            # The dispatch should be <= expected (might be less if load is lower)
            if actual_total > expected_total + 1e-6:
                print(f"   ✗ Dispatch exceeds maximum allowed by constraints")
                return False
            
            return True
    else:
        print("   ✗ No dispatch data found")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("HYDRO TIME SERIES CONVERSION TEST")
    print("=" * 80)
    
    # Test 1: Time series conversion
    test1_passed = test_hydro_timeseries_conversion()
    
    # Test 2: Dispatch after optimization
    test2_passed = test_hydro_dispatch_after_optimization()
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Time series conversion: {'✓ PASSED' if test1_passed else '✗ FAILED'}")
    print(f"Dispatch constraints: {'✓ PASSED' if test2_passed else '✗ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n✓ All tests passed!")
        exit(0)
    else:
        print("\n✗ Some tests failed")
        exit(1)

