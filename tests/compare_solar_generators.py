#!/usr/bin/env python3
"""
Compare solar generators between PyPSA and Sienna systems.

This script loads the systems from files (doesn't re-run conversion) and compares:
- Marginal costs
- Capacity factors (time series)
- Max capacity
- Total solar dispatch (from dispatch CSV files)
"""

import pypsa
import pandas as pd
import numpy as np
from pathlib import Path
from r2x.api import System
from r2x.models import RenewableDispatch
from r2x.enums import PrimeMoversType
from loguru import logger

# File paths
TEST_DATA_DIR = Path(__file__).parent / "test_output"
PYPSA_NETCDF = Path(__file__).parent / "data" / "elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc"
SIENNA_JSON = TEST_DATA_DIR / "elec_s380_c7a_ec_lv1_output_optimized.json"
PYPSA_DISPATCH = TEST_DATA_DIR / "pypsa_dispatch.csv"
SIENNA_DISPATCH = TEST_DATA_DIR / "sienna_dispatch.csv"

def load_pypsa_system():
    """Load PyPSA network from NetCDF file."""
    if not PYPSA_NETCDF.exists():
        raise FileNotFoundError(f"PyPSA NetCDF file not found: {PYPSA_NETCDF}")
    
    logger.info(f"Loading PyPSA network from: {PYPSA_NETCDF}")
    network = pypsa.Network(str(PYPSA_NETCDF))
    return network

def load_sienna_system():
    """Load Sienna system from JSON file."""
    if not SIENNA_JSON.exists():
        raise FileNotFoundError(f"Sienna JSON file not found: {SIENNA_JSON}")
    
    logger.info(f"Loading Sienna system from: {SIENNA_JSON}")
    sys = System(str(SIENNA_JSON))
    # Set NATURAL_UNITS for consistent comparison (if method exists)
    try:
        sys.set_units_base_system("NATURAL_UNITS")
    except AttributeError:
        # Method might not be available in Python API, but get_max_active_power() should still work
        logger.warning("set_units_base_system() not available, assuming NATURAL_UNITS")
    return sys

def get_pypsa_solar_generators(network):
    """Extract solar generator information from PyPSA network."""
    # Filter for solar generators (carrier contains "pve" or "solar")
    solar_gens = network.generators[
        network.generators["carrier"].str.lower().str.contains("pve|solar", na=False)
    ].copy()
    
    logger.info(f"Found {len(solar_gens)} solar generators in PyPSA")
    
    # Get capacity factors from time series
    solar_data = []
    for gen_name in solar_gens.index:
        gen = solar_gens.loc[gen_name]
        
        # Get static properties
        p_nom = gen.get("p_nom", 0.0)
        marginal_cost = gen.get("marginal_cost", 0.0)
        
        # Get capacity factor time series if available
        capacity_factors = None
        if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_max_pu'):
            if gen_name in network.generators_t.p_max_pu.columns:
                capacity_factors = network.generators_t.p_max_pu[gen_name]
        
        solar_data.append({
            'name': gen_name,
            'p_nom': p_nom,
            'marginal_cost': marginal_cost,
            'capacity_factors': capacity_factors,
            'max_capacity': p_nom,  # Max capacity = p_nom (nameplate)
        })
    
    return pd.DataFrame(solar_data)

def get_sienna_solar_generators(sys):
    """Extract solar generator information from Sienna system."""
    # Debug: Check what generator types exist
    from r2x.models import ThermalStandard, Generator
    all_generators = list(sys.get_components(Generator))
    thermal_gens = list(sys.get_components(ThermalStandard))
    renewable_gens = list(sys.get_components(RenewableDispatch))
    
    logger.info(f"Total generators: {len(all_generators)}")
    logger.info(f"ThermalStandard: {len(thermal_gens)}")
    logger.info(f"RenewableDispatch: {len(renewable_gens)}")
    
    # Get all RenewableDispatch generators
    all_renewable = renewable_gens
    
    # Debug: Check what prime mover types we have
    prime_mover_types = {}
    for g in all_renewable:
        pm_type = str(g.prime_mover_type)
        prime_mover_types[pm_type] = prime_mover_types.get(pm_type, 0) + 1
    
    logger.info(f"Found {len(all_renewable)} RenewableDispatch generators")
    logger.info(f"Prime mover types: {prime_mover_types}")
    
    # Filter for solar (prime mover type PVe)
    # prime_mover_type can be stored as enum or string in JSON
    solar_gens = []
    for g in all_renewable:
        pm_type = g.prime_mover_type
        # Check if it's PVe (either as enum or string)
        pm_str = str(pm_type)
        if pm_type == PrimeMoversType.PVe or pm_str == "PVe" or pm_str.endswith("PVe") or pm_str == "PrimeMoversType.PVe":
            solar_gens.append(g)
    
    logger.info(f"Found {len(solar_gens)} solar generators in Sienna")
    
    solar_data = []
    for gen in solar_gens:
        # Get static properties
        name = gen.name
        base_power = gen.base_power.magnitude if hasattr(gen.base_power, 'magnitude') else gen.base_power
        rating = gen.rating.magnitude if hasattr(gen.rating, 'magnitude') else gen.rating
        power_factor = gen.power_factor
        
        # Get max capacity using get_max_active_power() (what PowerSimulations uses)
        # This returns MW with NATURAL_UNITS: rating * power_factor * base_power
        try:
            max_capacity = gen.get_max_active_power().magnitude if hasattr(gen.get_max_active_power(), 'magnitude') else gen.get_max_active_power()
        except:
            # Fallback to manual calculation
            max_capacity = rating * power_factor * base_power
        
        # Get marginal cost
        marginal_cost = 0.0
        if gen.operation_cost and hasattr(gen.operation_cost, 'variable'):
            if gen.operation_cost.variable and hasattr(gen.operation_cost.variable, 'value_curve'):
                if hasattr(gen.operation_cost.variable.value_curve, 'slope'):
                    marginal_cost = gen.operation_cost.variable.value_curve.slope
        
        # Get capacity factor time series if available
        capacity_factors = None
        time_series_list = list(sys.list_time_series(gen))
        for ts in time_series_list:
            if ts.name == "max_active_power":
                # Time series is in per-unit (0-1)
                capacity_factors = ts.data
                break
        
        solar_data.append({
            'name': name,
            'p_nom': base_power,  # base_power is the nameplate capacity
            'marginal_cost': marginal_cost,
            'capacity_factors': capacity_factors,
            'max_capacity': max_capacity,
            'rating': rating,
            'power_factor': power_factor,
        })
    
    return pd.DataFrame(solar_data)

def compare_solar_generators(pypsa_df, sienna_df):
    """Compare solar generators between PyPSA and Sienna."""
    print("\n" + "="*80)
    print("SOLAR GENERATOR COMPARISON")
    print("="*80)
    
    # Check if we have any data
    if len(pypsa_df) == 0:
        print("⚠️  No PyPSA solar generators found!")
        return
    if len(sienna_df) == 0:
        print("⚠️  No Sienna solar generators found!")
        print("  This might indicate a conversion issue or prime_mover_type mismatch.")
        return
    
    # Match generators by name (they should have the same names)
    pypsa_df = pypsa_df.set_index('name')
    sienna_df = sienna_df.set_index('name')
    
    common_names = set(pypsa_df.index) & set(sienna_df.index)
    only_pypsa = set(pypsa_df.index) - set(sienna_df.index)
    only_sienna = set(sienna_df.index) - set(pypsa_df.index)
    
    print(f"\nGenerator matching:")
    print(f"  Common generators: {len(common_names)}")
    if only_pypsa:
        print(f"  ⚠️  Only in PyPSA: {len(only_pypsa)} generators")
        print(f"     {list(only_pypsa)[:5]}")
    if only_sienna:
        print(f"  ⚠️  Only in Sienna: {len(only_sienna)} generators")
        print(f"     {list(only_sienna)[:5]}")
    
    # Compare marginal costs
    print(f"\n{'='*80}")
    print("MARGINAL COST COMPARISON")
    print(f"{'='*80}")
    
    marginal_cost_comparison = []
    for name in common_names:
        pypsa_mc = pypsa_df.loc[name, 'marginal_cost']
        sienna_mc = sienna_df.loc[name, 'marginal_cost']
        diff = abs(pypsa_mc - sienna_mc)
        marginal_cost_comparison.append({
            'name': name,
            'pypsa_marginal_cost': pypsa_mc,
            'sienna_marginal_cost': sienna_mc,
            'difference': diff,
        })
    
    mc_df = pd.DataFrame(marginal_cost_comparison)
    print(f"\nMarginal cost statistics:")
    print(f"  PyPSA: min={mc_df['pypsa_marginal_cost'].min():.6f}, max={mc_df['pypsa_marginal_cost'].max():.6f}, mean={mc_df['pypsa_marginal_cost'].mean():.6f}")
    print(f"  Sienna: min={mc_df['sienna_marginal_cost'].min():.6f}, max={mc_df['sienna_marginal_cost'].max():.6f}, mean={mc_df['sienna_marginal_cost'].mean():.6f}")
    print(f"  Differences: max={mc_df['difference'].max():.6f}, mean={mc_df['difference'].mean():.6f}")
    
    # Check if all costs are identical
    if mc_df['difference'].max() < 1e-6:
        print(f"  ✓ All marginal costs match!")
    else:
        print(f"  ⚠️  Marginal cost differences found!")
        print(f"\n  Generators with different marginal costs:")
        differing = mc_df[mc_df['difference'] > 1e-6]
        print(differing.to_string(index=False))
    
    # Compare capacities
    print(f"\n{'='*80}")
    print("CAPACITY COMPARISON")
    print(f"{'='*80}")
    
    capacity_comparison = []
    for name in common_names:
        pypsa_p_nom = pypsa_df.loc[name, 'p_nom']
        sienna_p_nom = sienna_df.loc[name, 'p_nom']
        pypsa_max = pypsa_df.loc[name, 'max_capacity']
        sienna_max = sienna_df.loc[name, 'max_capacity']
        
        capacity_comparison.append({
            'name': name,
            'pypsa_p_nom': pypsa_p_nom,
            'sienna_p_nom': sienna_p_nom,
            'pypsa_max_capacity': pypsa_max,
            'sienna_max_capacity': sienna_max,
            'p_nom_diff': abs(pypsa_p_nom - sienna_p_nom),
            'max_capacity_diff': abs(pypsa_max - sienna_max),
        })
    
    cap_df = pd.DataFrame(capacity_comparison)
    print(f"\nCapacity statistics:")
    print(f"  PyPSA p_nom: total={cap_df['pypsa_p_nom'].sum():.2f} MW, mean={cap_df['pypsa_p_nom'].mean():.2f} MW")
    print(f"  Sienna p_nom: total={cap_df['sienna_p_nom'].sum():.2f} MW, mean={cap_df['sienna_p_nom'].mean():.2f} MW")
    print(f"  p_nom differences: max={cap_df['p_nom_diff'].max():.6f} MW, mean={cap_df['p_nom_diff'].mean():.6f} MW")
    print(f"  Max capacity differences: max={cap_df['max_capacity_diff'].max():.6f} MW, mean={cap_df['max_capacity_diff'].mean():.6f} MW")
    
    if cap_df['p_nom_diff'].max() < 1e-3:
        print(f"  ✓ All p_nom values match!")
    else:
        print(f"  ⚠️  p_nom differences found!")
        differing = cap_df[cap_df['p_nom_diff'] > 1e-3]
        print(f"\n  Generators with different p_nom (first 10):")
        print(differing[['name', 'pypsa_p_nom', 'sienna_p_nom', 'p_nom_diff']].head(10).to_string(index=False))
    
    if cap_df['max_capacity_diff'].max() < 1e-3:
        print(f"  ✓ All max_capacity values match!")
    else:
        print(f"  ⚠️  max_capacity differences found!")
        differing = cap_df[cap_df['max_capacity_diff'] > 1e-3]
        print(f"\n  Generators with different max_capacity (first 10):")
        print(differing[['name', 'pypsa_max_capacity', 'sienna_max_capacity', 'max_capacity_diff']].head(10).to_string(index=False))
    
    # Compare capacity factor time series
    print(f"\n{'='*80}")
    print("CAPACITY FACTOR TIME SERIES COMPARISON")
    print(f"{'='*80}")
    
    ts_comparison = []
    for name in common_names:
        pypsa_cf = pypsa_df.loc[name, 'capacity_factors']
        sienna_cf = sienna_df.loc[name, 'capacity_factors']
        
        if pypsa_cf is None and sienna_cf is None:
            ts_comparison.append({
                'name': name,
                'pypsa_has_ts': False,
                'sienna_has_ts': False,
                'ts_match': True,
            })
        elif pypsa_cf is None:
            ts_comparison.append({
                'name': name,
                'pypsa_has_ts': False,
                'sienna_has_ts': True,
                'ts_match': False,
            })
        elif sienna_cf is None:
            ts_comparison.append({
                'name': name,
                'pypsa_has_ts': True,
                'sienna_has_ts': False,
                'ts_match': False,
            })
        else:
            # Both have time series - compare values
            # Convert to numpy arrays for comparison
            if hasattr(pypsa_cf, 'values'):
                pypsa_values = pypsa_cf.values
            else:
                pypsa_values = np.array(pypsa_cf)
            
            if hasattr(sienna_cf, 'values'):
                sienna_values = sienna_cf.values
            else:
                sienna_values = np.array(sienna_cf)
            
            # Check if lengths match
            if len(pypsa_values) != len(sienna_values):
                ts_comparison.append({
                    'name': name,
                    'pypsa_has_ts': True,
                    'sienna_has_ts': True,
                    'pypsa_length': len(pypsa_values),
                    'sienna_length': len(sienna_values),
                    'ts_match': False,
                    'max_diff': np.nan,
                    'mean_diff': np.nan,
                })
            else:
                # Compare values
                max_diff = np.max(np.abs(pypsa_values - sienna_values))
                mean_diff = np.mean(np.abs(pypsa_values - sienna_values))
                ts_match = max_diff < 1e-6
                
                ts_comparison.append({
                    'name': name,
                    'pypsa_has_ts': True,
                    'sienna_has_ts': True,
                    'pypsa_length': len(pypsa_values),
                    'sienna_length': len(sienna_values),
                    'ts_match': ts_match,
                    'max_diff': max_diff,
                    'mean_diff': mean_diff,
                    'pypsa_cf_max': np.max(pypsa_values),
                    'sienna_cf_max': np.max(sienna_values),
                    'pypsa_cf_mean': np.mean(pypsa_values),
                    'sienna_cf_mean': np.mean(sienna_values),
                })
    
    ts_df = pd.DataFrame(ts_comparison)
    
    print(f"\nTime series statistics:")
    print(f"  Generators with time series in PyPSA: {ts_df['pypsa_has_ts'].sum()}")
    print(f"  Generators with time series in Sienna: {ts_df['sienna_has_ts'].sum()}")
    print(f"  Generators with matching time series: {ts_df['ts_match'].sum()}")
    
    if ts_df['ts_match'].all():
        print(f"  ✓ All time series match!")
    else:
        print(f"  ⚠️  Time series differences found!")
        differing = ts_df[~ts_df['ts_match']]
        print(f"\n  Generators with different time series (first 10):")
        print(differing.to_string(index=False))
    
    # Compare total solar dispatch from CSV files
    print(f"\n{'='*80}")
    print("TOTAL SOLAR DISPATCH COMPARISON (from CSV files)")
    print(f"{'='*80}")
    
    if PYPSA_DISPATCH.exists() and SIENNA_DISPATCH.exists():
        pypsa_dispatch = pd.read_csv(PYPSA_DISPATCH)
        sienna_dispatch = pd.read_csv(SIENNA_DISPATCH)
        
        # Convert DateTime to datetime
        pypsa_dispatch['DateTime'] = pd.to_datetime(pypsa_dispatch['DateTime'])
        sienna_dispatch['DateTime'] = pd.to_datetime(sienna_dispatch['DateTime'])
        
        # Filter for solar (PVe)
        pypsa_solar = pypsa_dispatch[
            pypsa_dispatch['carrier'].str.lower().str.contains('pve', na=False)
        ]
        sienna_solar = sienna_dispatch[
            sienna_dispatch['carrier'].str.lower().str.contains('pve', na=False)
        ]
        
        # Sum by DateTime
        pypsa_total = pypsa_solar.groupby('DateTime')['value'].sum()
        sienna_total = sienna_solar.groupby('DateTime')['value'].sum()
        
        # Find common timesteps
        common_times = set(pypsa_total.index) & set(sienna_total.index)
        
        if common_times:
            comparison = pd.DataFrame({
                'pypsa_total': pypsa_total.reindex(common_times),
                'sienna_total': sienna_total.reindex(common_times),
            }).fillna(0.0)
            
            comparison['difference'] = comparison['pypsa_total'] - comparison['sienna_total']
            comparison['abs_difference'] = np.abs(comparison['difference'])
            comparison['rel_difference'] = (comparison['abs_difference'] / 
                                           np.maximum(comparison['pypsa_total'].abs(), 
                                                     comparison['sienna_total'].abs()) * 100)
            comparison['rel_difference'] = comparison['rel_difference'].fillna(0.0)
            
            print(f"\nDispatch statistics (over {len(common_times)} common timesteps):")
            print(f"  PyPSA total solar: min={comparison['pypsa_total'].min():.2f} MW, "
                  f"max={comparison['pypsa_total'].max():.2f} MW, "
                  f"mean={comparison['pypsa_total'].mean():.2f} MW")
            print(f"  Sienna total solar: min={comparison['sienna_total'].min():.2f} MW, "
                  f"max={comparison['sienna_total'].max():.2f} MW, "
                  f"mean={comparison['sienna_total'].mean():.2f} MW")
            print(f"  Differences: max_abs={comparison['abs_difference'].max():.6f} MW, "
                  f"mean_abs={comparison['abs_difference'].mean():.6f} MW")
            print(f"  Relative differences: max={comparison['rel_difference'].max():.4f}%, "
                  f"mean={comparison['rel_difference'].mean():.4f}%")
            
            # Check per-generator dispatch
            print(f"\n  Per-generator dispatch comparison:")
            pypsa_by_gen = pypsa_solar.groupby(['DateTime', 'name'])['value'].sum().reset_index()
            sienna_by_gen = sienna_solar.groupby(['DateTime', 'name'])['value'].sum().reset_index()
            
            # Merge on DateTime and name
            gen_comparison = pypsa_by_gen.merge(
                sienna_by_gen,
                on=['DateTime', 'name'],
                how='inner',
                suffixes=('_pypsa', '_sienna')
            )
            
            if len(gen_comparison) > 0:
                gen_comparison['difference'] = gen_comparison['value_pypsa'] - gen_comparison['value_sienna']
                gen_comparison['abs_difference'] = np.abs(gen_comparison['difference'])
                
                # Summary by generator
                gen_summary = gen_comparison.groupby('name').agg({
                    'value_pypsa': 'sum',
                    'value_sienna': 'sum',
                    'abs_difference': 'mean',
                }).reset_index()
                gen_summary['total_diff'] = gen_summary['value_pypsa'] - gen_summary['value_sienna']
                gen_summary['rel_diff_pct'] = (gen_summary['total_diff'] / 
                                               np.maximum(gen_summary['value_pypsa'].abs(),
                                                         gen_summary['value_sienna'].abs()) * 100)
                
                print(f"    Compared {len(gen_summary)} generators across {len(common_times)} timesteps")
                print(f"    Generators with largest differences:")
                print(gen_summary.nlargest(10, 'abs_difference')[['name', 'value_pypsa', 'value_sienna', 'total_diff', 'rel_diff_pct']].to_string(index=False))
        else:
            print(f"  ⚠️  No common timesteps found between dispatch files!")
    else:
        print(f"  ⚠️  Dispatch CSV files not found!")
        if not PYPSA_DISPATCH.exists():
            print(f"     Missing: {PYPSA_DISPATCH}")
        if not SIENNA_DISPATCH.exists():
            print(f"     Missing: {SIENNA_DISPATCH}")
    
    print(f"\n{'='*80}")
    print("COMPARISON COMPLETE")
    print(f"{'='*80}\n")

def main():
    """Main function to run the comparison."""
    try:
        # Load systems
        network = load_pypsa_system()
        sys = load_sienna_system()
        
        # Extract solar generator data
        pypsa_solar = get_pypsa_solar_generators(network)
        sienna_solar = get_sienna_solar_generators(sys)
        
        # Compare
        compare_solar_generators(pypsa_solar, sienna_solar)
        
    except Exception as e:
        logger.error(f"Error during comparison: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()

