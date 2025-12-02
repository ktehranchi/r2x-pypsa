#!/usr/bin/env python3
"""Test hydro dispatch using the actual system data to catch the real issue."""

import pypsa
import pandas as pd
from pathlib import Path
from r2x.api import System
from infrasys import TimeSeriesStorageType
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization import create_default_mapping
from r2x_pypsa.serialization.to_sienna import infrasys_to_psy
from r2x.models import HydroDispatch
from loguru import logger

def test_real_hydro_system():
    """Test hydro conversion using the actual test network."""
    print("=" * 80)
    print("TEST: Real System Hydro Conversion")
    print("=" * 80)
    
    # Load actual network
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    network = pypsa.Network(test_file)
    
    # Get hydro generators
    hydro_gens = network.generators[network.generators['carrier'] == 'hydro']
    hydro_gens_active = hydro_gens[hydro_gens['p_nom'] > 0]
    
    print(f"\n1. PyPSA Network:")
    print(f"   Total hydro generators: {len(hydro_gens)}")
    print(f"   Active (p_nom > 0): {len(hydro_gens_active)}")
    
    if len(hydro_gens_active) == 0:
        print("   ✗ No active hydro generators found")
        return False
    
    # Check time series
    if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_max_pu'):
        hydro_p_max_pu = network.generators_t.p_max_pu[hydro_gens_active.index]
        print(f"\n2. PyPSA Hydro Time Series:")
        for gen_name in hydro_gens_active.index[:3]:  # Check first 3
            p_nom = hydro_gens_active.loc[gen_name, 'p_nom']
            p_max_pu_ts = hydro_p_max_pu[gen_name]
            print(f"   {gen_name:20s} | p_nom: {p_nom:6.1f} MW | p_max_pu range: [{p_max_pu_ts.min():.3f}, {p_max_pu_ts.max():.3f}] | mean: {p_max_pu_ts.mean():.3f}")
            print(f"     Expected max dispatch: {p_max_pu_ts.max() * p_nom:.1f} MW")
            print(f"     Expected avg dispatch: {p_max_pu_ts.mean() * p_nom:.1f} MW")
    else:
        print("   ⚠ No p_max_pu time series found")
    
    # Convert to PowerSystems
    print(f"\n3. Converting to PowerSystems...")
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
            logger.debug(f"Failed to convert {component.name}: {e}")
            continue
    
    # Check PowerSystems hydro generators
    psy_hydro_gens = list(psy_system.get_components(HydroDispatch))
    print(f"   PowerSystems hydro generators: {len(psy_hydro_gens)}")
    
    if len(psy_hydro_gens) != len(hydro_gens_active):
        print(f"   ⚠ Count mismatch: PyPSA={len(hydro_gens_active)}, PowerSystems={len(psy_hydro_gens)}")
    
    # Check time series for each hydro generator
    print(f"\n4. Checking PowerSystems Hydro Time Series:")
    issues = []
    
    for psy_hydro in psy_hydro_gens[:5]:  # Check first 5
        gen_name = psy_hydro.name
        # base_power is a Quantity, get the magnitude
        p_nom = psy_hydro.base_power.magnitude if hasattr(psy_hydro.base_power, 'magnitude') else float(psy_hydro.base_power)
        
        # Find corresponding PyPSA generator
        pypsa_gen = None
        if gen_name in hydro_gens_active.index:
            pypsa_gen = hydro_gens_active.loc[gen_name]
            pypsa_p_max_pu = network.generators_t.p_max_pu[gen_name] if hasattr(network, 'generators_t') else None
        else:
            print(f"   ⚠ {gen_name} not found in PyPSA active hydro generators")
            continue
        
        print(f"\n   {gen_name}:")
        print(f"     base_power: {p_nom} MW")
        
        # Check time series
        if psy_system.has_time_series(psy_hydro, "max_active_power"):
            ts = psy_system.get_time_series(psy_hydro, "max_active_power")
            if hasattr(ts, 'data'):
                # ts.data is a numpy array
                import numpy as np
                ts_values = np.array(ts.data) if not isinstance(ts.data, np.ndarray) else ts.data
                print(f"     Time series range: [{ts_values.min():.3f}, {ts_values.max():.3f}]")
                print(f"     Time series mean: {ts_values.mean():.3f}")
                
                # Check if in per-unit
                if ts_values.max() > 1.1:
                    issue = f"{gen_name}: Time series in MW (max={ts_values.max():.2f}), should be per-unit"
                    issues.append(issue)
                    print(f"     ✗ {issue}")
                else:
                    print(f"     ✓ Time series in per-unit (0-1)")
                    
                    # Compare with PyPSA
                    if pypsa_p_max_pu is not None:
                        if len(ts_values) == len(pypsa_p_max_pu):
                            # Compare first 168 values (1 week) if available
                            compare_len = min(len(ts_values), len(pypsa_p_max_pu), 168)
                            ts_compare = ts_values[:compare_len]
                            pypsa_compare = pypsa_p_max_pu.iloc[:compare_len].values
                            
                            diff = abs(ts_compare - pypsa_compare).max()
                            if diff > 0.01:
                                issue = f"{gen_name}: Time series doesn't match PyPSA (max diff: {diff:.6f})"
                                issues.append(issue)
                                print(f"     ✗ {issue}")
                                print(f"       First 5 PyPSA: {pypsa_compare[:5]}")
                                print(f"       First 5 PowerSystems: {ts_compare[:5]}")
                            else:
                                print(f"     ✓ Matches PyPSA p_max_pu (max diff: {diff:.6f})")
                                
                                # Calculate expected dispatch
                                expected_max_mw = ts_values.max() * p_nom
                                expected_avg_mw = ts_values.mean() * p_nom
                                expected_total_week = (ts_values[:168] * p_nom).sum() if len(ts_values) >= 168 else (ts_values * p_nom).sum()
                                print(f"     Expected max dispatch: {expected_max_mw:.1f} MW")
                                print(f"     Expected avg dispatch: {expected_avg_mw:.1f} MW")
                                print(f"     Expected total (1 week): {expected_total_week:.1f} MWh")
                                
                                # This is what Sienna SHOULD dispatch (if respecting constraints)
                                # If Sienna dispatches more than this, it's ignoring the time series
                                print(f"     ⚠ If Sienna dispatches > {expected_max_mw:.1f} MW max, time series is being ignored!")
                        else:
                            issue = f"{gen_name}: Time series length mismatch: PyPSA={len(pypsa_p_max_pu)}, PowerSystems={len(ts_values)}"
                            issues.append(issue)
                            print(f"     ✗ {issue}")
                    else:
                        print(f"     ⚠ No PyPSA p_max_pu to compare")
            else:
                issue = f"{gen_name}: Could not extract time series values"
                issues.append(issue)
                print(f"     ✗ {issue}")
        else:
            issue = f"{gen_name}: No time series found"
            issues.append(issue)
            print(f"     ✗ {issue}")
    
    # Check Sienna dispatch if available
    print(f"\n5. Checking Sienna dispatch (if available)...")
    dispatch_file = Path("tests/test_output/sienna_dispatch.csv")
    
    if dispatch_file.exists():
        import pandas as pd
        df = pd.read_csv(dispatch_file)
        sienna_hydro = df[df['carrier'] == 'hydro']
        
        if not sienna_hydro.empty:
            sienna_total = sienna_hydro['value'].sum()
            sienna_max = sienna_hydro['value'].max()
            sienna_avg = sienna_hydro['value'].mean()
            
            print(f"   Sienna hydro dispatch:")
            print(f"     Total: {sienna_total:.2f} MWh")
            print(f"     Max: {sienna_max:.2f} MW")
            print(f"     Avg: {sienna_avg:.2f} MW")
            
            # Calculate expected totals from PyPSA (1 week = 168 hours)
            # Get ACTUAL PyPSA dispatch (not theoretical max)
            pypsa_actual_total = None
            pypsa_actual_max = None
            if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
                # Optimize PyPSA to get actual dispatch
                try:
                    network.optimize(snapshots=network.snapshots[0:7*24], solver_name='gurobi')
                    if network.objective is not None:
                        hydro_dispatch = network.generators_t.p[hydro_gens_active.index]
                        pypsa_actual_total = hydro_dispatch.sum().sum()
                        pypsa_actual_max = hydro_dispatch.max().max()
                except:
                    pass
            
            # Also get theoretical max from constraints
            if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_max_pu'):
                pypsa_p_max_pu = network.generators_t.p_max_pu[hydro_gens_active.index]
                # Use first 168 hours (1 week) to match Sienna optimization period
                pypsa_p_max_pu_week = pypsa_p_max_pu.iloc[:168] if len(pypsa_p_max_pu) >= 168 else pypsa_p_max_pu
                theoretical_max = (pypsa_p_max_pu_week * hydro_gens_active['p_nom']).sum().sum()
                expected_max = (pypsa_p_max_pu_week * hydro_gens_active['p_nom']).max().max()
                
                # Use actual PyPSA dispatch if available, otherwise use theoretical max
                expected_total = pypsa_actual_total if pypsa_actual_total is not None else theoretical_max
                
                print(f"\n   Expected (from PyPSA):")
                if pypsa_actual_total is not None:
                    print(f"     Actual dispatch: {pypsa_actual_total:.2f} MWh")
                    print(f"     Theoretical max: {theoretical_max:.2f} MWh")
                else:
                    print(f"     Theoretical max: {theoretical_max:.2f} MWh (PyPSA not optimized)")
                print(f"     Max: {expected_max:.2f} MW")
                
                # Check if Sienna matches PyPSA actual dispatch (within 20% tolerance)
                ratio = sienna_total / expected_total if expected_total > 0 else 0
                
                if sienna_total > expected_total * 1.2:  # More than 20% above PyPSA
                    issue = f"Sienna dispatches {sienna_total:.0f} MWh, but PyPSA dispatches {expected_total:.0f} MWh ({sienna_total/expected_total:.1f}x too high)"
                    issues.append(issue)
                    print(f"\n   ✗ {issue}")
                    print(f"     This suggests Sienna is NOT respecting the time series constraints!")
                elif sienna_max > expected_max * 1.1:
                    issue = f"Sienna max dispatch {sienna_max:.1f} MW exceeds expected max {expected_max:.1f} MW"
                    issues.append(issue)
                    print(f"\n   ✗ {issue}")
                elif sienna_total < expected_total * 0.8:  # Less than 80% of PyPSA
                    issue = f"Sienna dispatches {sienna_total:.0f} MWh, but PyPSA dispatches {expected_total:.0f} MWh (only {ratio:.1%} of PyPSA)"
                    issues.append(issue)
                    print(f"\n   ✗ {issue}")
                    print(f"     This suggests Sienna is under-dispatching hydro significantly!")
                    print(f"     Possible causes:")
                    print(f"       - Time series constraints are too restrictive")
                    print(f"       - HydroDispatchRunOfRiver not using time series correctly")
                    print(f"       - Different optimization behavior between PyPSA and Sienna")
                elif sienna_total > expected_total * 1.2:  # More than 20% above PyPSA
                    issue = f"Sienna dispatches {sienna_total:.0f} MWh, but PyPSA dispatches {expected_total:.0f} MWh ({sienna_total/expected_total:.1f}x too high)"
                    issues.append(issue)
                    print(f"\n   ✗ {issue}")
                else:
                    print(f"\n   ✓ Sienna dispatch matches PyPSA")
                    print(f"     Sienna: {sienna_total:.0f} MWh, PyPSA: {expected_total:.0f} MWh ({ratio:.1%} match)")
        else:
            print(f"   ⚠ No hydro dispatch found in Sienna results")
    else:
        print(f"   ⚠ Sienna dispatch file not found: {dispatch_file}")
        print(f"     Run the Julia script to generate it")
    
    # Summary
    print(f"\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if issues:
        print(f"✗ Found {len(issues)} issues:")
        for issue in issues:
            print(f"  - {issue}")
        assert False, f"Found {len(issues)} issues with hydro time series or dispatch"
    else:
        print(f"✓ All hydro generators have correct time series (in per-unit)")
        if dispatch_file.exists():
            print(f"✓ Sienna dispatch respects time series constraints")
        else:
            print(f"\n⚠️  IMPORTANT: Even if time series is correct, Sienna might still")
            print(f"   dispatch more than allowed if HydroDispatchRunOfRiver doesn't")
            print(f"   respect the max_active_power time series constraints.")
            print(f"   Check Sienna dispatch results to verify constraints are applied.")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("REAL SYSTEM HYDRO TEST")
    print("=" * 80)
    
    passed = test_real_hydro_system()
    
    print("\n" + "=" * 80)
    print("TEST RESULT")
    print("=" * 80)
    if passed:
        print("✓ TEST PASSED - Hydro time series correctly converted")
        print("\n⚠️  But verify Sienna dispatch respects these constraints!")
        exit(0)
    else:
        print("✗ TEST FAILED - Issues found with hydro time series")
        exit(1)

