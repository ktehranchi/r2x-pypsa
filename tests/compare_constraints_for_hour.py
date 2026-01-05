"""Compare actual constraint values for a specific hour between PyPSA and Sienna.

This script extracts and compares:
- Capacity limits (p_max_pu * p_nom)
- Actual dispatch
- Whether constraints are binding
- Load values
"""

import pypsa
import pandas as pd
import json
import h5py
import sqlite3
from pathlib import Path
from loguru import logger
import numpy as np

def extract_pypsa_constraints(network, target_hour):
    """Extract constraint values from PyPSA for a specific hour.
    
    Parameters
    ----------
    network : pypsa.Network
        Optimized PyPSA network
    target_hour : pd.Timestamp
        Target hour to analyze
        
    Returns
    -------
    dict
        Dictionary with constraint values
    """
    # Find matching snapshot - handle both tuple (MultiIndex) and datetime formats
    if len(network.snapshots) > 0:
        # Check if snapshots are tuples (MultiIndex format)
        if isinstance(network.snapshots[0], tuple):
            # Extract datetime from tuple (usually second element)
            network_snapshots = pd.to_datetime([s[1] if len(s) >= 2 else s[0] for s in network.snapshots])
        else:
            # Already datetime objects
            network_snapshots = pd.to_datetime(network.snapshots)
    else:
        network_snapshots = pd.DatetimeIndex([])
    
    if len(network_snapshots) == 0:
        logger.error("No snapshots found in network")
        return {}
    
    # Find closest snapshot
    time_diffs = pd.Series([abs((ts - target_hour).total_seconds()) for ts in network_snapshots])
    closest_idx = time_diffs.idxmin()
    snapshot = network_snapshots[closest_idx]
    
    # Get the actual snapshot value (might be tuple or datetime)
    if isinstance(network.snapshots[0], tuple):
        snapshot_value = network.snapshots[closest_idx]
    else:
        snapshot_value = snapshot
    
    logger.info(f"Target hour: {target_hour}")
    logger.info(f"PyPSA snapshot: {snapshot}")
    
    # Get renewable generators
    renewable_carriers = ['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'hydro', 'ror']
    renewable_gens = network.generators[
        (network.generators.carrier.isin(renewable_carriers)) & 
        (network.generators.p_nom > 0)
    ].copy()
    
    constraints = {
        'snapshot': snapshot,
        'generators': {},
        'total_load': 0.0,
        'total_renewable_dispatch': 0.0,
        'total_renewable_capacity': 0.0,
    }
    
    # Extract capacity limits and dispatch for each generator
    for gen_name in renewable_gens.index:
        gen = renewable_gens.loc[gen_name]
        p_nom = gen.p_nom
        
        # Get capacity limit (p_max_pu * p_nom)
        if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_max_pu'):
            if gen_name in network.generators_t.p_max_pu.columns:
                p_max_pu = network.generators_t.p_max_pu.loc[snapshot_value, gen_name]
                capacity_limit = p_max_pu * p_nom
            else:
                # No time series, use static p_max_pu
                p_max_pu = gen.get('p_max_pu', 1.0)
                capacity_limit = p_max_pu * p_nom
        else:
            p_max_pu = gen.get('p_max_pu', 1.0)
            capacity_limit = p_max_pu * p_nom
        
        # Get actual dispatch
        if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
            if gen_name in network.generators_t.p.columns:
                dispatch = network.generators_t.p.loc[snapshot_value, gen_name]
            else:
                dispatch = 0.0
        else:
            dispatch = 0.0
        
        # Check if binding (dispatch at limit, within tolerance)
        tolerance = 0.01  # MW
        is_binding = abs(dispatch - capacity_limit) < tolerance
        
        constraints['generators'][gen_name] = {
            'carrier': gen.carrier,
            'p_nom': p_nom,
            'p_max_pu': p_max_pu,
            'capacity_limit': capacity_limit,
            'dispatch': dispatch,
            'is_binding': is_binding,
            'utilization': dispatch / capacity_limit if capacity_limit > 0 else 0.0,
        }
        
        constraints['total_renewable_dispatch'] += dispatch
        constraints['total_renewable_capacity'] += capacity_limit
    
    # Get total load
    if hasattr(network, 'loads_t') and hasattr(network.loads_t, 'p_set'):
        constraints['total_load'] = network.loads_t.p_set.loc[snapshot_value].sum()
    
    return constraints


def extract_sienna_constraints(json_file, h5_file, dispatch_file, target_hour):
    """Extract constraint values from Sienna for a specific hour.
    
    Parameters
    ----------
    json_file : Path
        Path to Sienna JSON file
    h5_file : Path
        Path to Sienna HDF5 file
    dispatch_file : Path
        Path to Sienna dispatch CSV file
    target_hour : pd.Timestamp
        Target hour to analyze
        
    Returns
    -------
    dict
        Dictionary with constraint values
    """
    # Load JSON
    with open(json_file) as f:
        sienna_data = json.load(f)
    
    components = sienna_data.get('data', {}).get('components', [])
    
    # Get renewable generators
    renewable_gens = {
        g.get('name'): g
        for g in components
        if g.get('__metadata__', {}).get('type') == 'RenewableDispatch'
    }
    
    # Check for hydro generators that might also be stored as EnergyReservoirStorage
    storage_components = [
        c for c in components
        if c.get('__metadata__', {}).get('type') == 'EnergyReservoirStorage'
    ]
    
    # Check if any storage components have the same name as renewable generators (hydro double-counting)
    renewable_names = set(renewable_gens.keys())
    storage_names = {s.get('name') for s in storage_components}
    hydro_storage_overlap = renewable_names & storage_names
    
    if hydro_storage_overlap:
        logger.warning(f"⚠️  Found {len(hydro_storage_overlap)} components that exist as both RenewableDispatch and EnergyReservoirStorage:")
        for name in sorted(hydro_storage_overlap)[:10]:
            renewable_gen = renewable_gens.get(name)
            storage_comp = next((s for s in storage_components if s.get('name') == name), None)
            if renewable_gen and storage_comp:
                renewable_carrier = renewable_gen.get('prime_mover_type', 'unknown')
                logger.warning(f"  - {name}: RenewableDispatch (prime_mover={renewable_carrier}) AND EnergyReservoirStorage")
                constraints['hydro_as_storage'].append(name)
    
    constraints = {
        'target_hour': target_hour,
        'generators': {},
        'total_load': 0.0,
        'total_renewable_dispatch': 0.0,
        'total_renewable_capacity': 0.0,
        'hydro_as_storage': [],  # Track hydro generators that might be counted as storage
    }
    
    # Load dispatch data
    dispatch_df = pd.read_csv(dispatch_file)
    dispatch_df['DateTime'] = pd.to_datetime(dispatch_df['DateTime'])
    
    # Find closest hour in dispatch data
    dispatch_snapshots = pd.to_datetime(dispatch_df['DateTime'].unique())
    time_diffs = pd.Series([abs((ts - target_hour).total_seconds()) for ts in dispatch_snapshots])
    closest_idx = time_diffs.idxmin()
    dispatch_hour = dispatch_snapshots[closest_idx]
    
    logger.info(f"Sienna dispatch hour: {dispatch_hour}")
    
    # Extract capacity limits and dispatch for each generator
    if h5_file.exists():
        with h5py.File(h5_file, 'r') as h5:
            if 'time_series_metadata' in h5:
                db_data = h5['time_series_metadata'][()]
                db_path = Path(".temp_constraints_analysis.db")
                
                with open(db_path, 'wb') as db_file:
                    db_file.write(bytes(db_data))
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                table_name = 'time_series_metadata' if 'time_series_metadata' in tables else 'time_series_associations'
                
                for gen_name, gen in renewable_gens.items():
                    gen_uuid = gen.get('internal', {}).get('uuid', {}).get('value')
                    if not gen_uuid:
                        continue
                    
                    # Get capacity parameters
                    base_power = gen.get('base_power', 0.0)
                    rating = gen.get('rating', 0.0)
                    power_factor = gen.get('power_factor', 1.0)
                    max_active_power = rating * base_power * power_factor
                    
                    # Get capacity factor time series
                    query = f'''
                        SELECT time_series_uuid, initial_timestamp, resolution, length
                        FROM {table_name}
                        WHERE owner_uuid = ? AND owner_type = 'RenewableDispatch' AND name = 'max_active_power'
                    '''
                    cursor.execute(query, (gen_uuid,))
                    result = cursor.fetchone()
                    
                    capacity_factor = 1.0  # Default if no time series
                    if result:
                        ts_uuid, initial_timestamp, resolution, length = result
                        
                        # Read time series data
                        possible_paths = [
                            f"/time_series/{ts_uuid}/data",
                            f"/time_series/{ts_uuid}",
                            f"/{ts_uuid}/data",
                        ]
                        
                        ts_data = None
                        for path in possible_paths:
                            if path in h5:
                                if isinstance(h5[path], h5py.Dataset):
                                    ts_data = h5[path][:]
                                    break
                                elif isinstance(h5[path], h5py.Group) and 'data' in h5[path]:
                                    ts_data = h5[path]['data'][:]
                                    break
                        
                        if ts_data is None and 'time_series' in h5:
                            for key in h5['time_series'].keys():
                                if ts_uuid in key or key == ts_uuid:
                                    ts_group = h5['time_series'][key]
                                    if 'data' in ts_group:
                                        ts_data = ts_group['data'][:]
                                        break
                                    elif isinstance(ts_group, h5py.Dataset):
                                        ts_data = ts_group[:]
                                        break
                        
                        if ts_data is not None:
                            # Find index for target hour
                            initial_ts = pd.Timestamp(initial_timestamp)
                            resolution_str = str(resolution)
                            if 'PT' in resolution_str:
                                resolution_str = resolution_str.replace('PT', '')
                                if 'H' in resolution_str:
                                    hours = int(resolution_str.replace('H', ''))
                                    freq = f"{hours}h"
                                else:
                                    freq = "1h"
                            else:
                                freq = "1h"
                            
                            time_index = pd.date_range(start=initial_ts, periods=len(ts_data), freq=freq)
                            
                            # Find closest time
                            time_diffs = pd.Series([abs((ts - dispatch_hour).total_seconds()) for ts in time_index])
                            closest_ts_idx = time_diffs.idxmin()
                            if closest_ts_idx < len(ts_data):
                                capacity_factor = float(ts_data[closest_ts_idx])
                    
                    capacity_limit = capacity_factor * max_active_power
                    
                    # Get dispatch from CSV
                    gen_dispatch = dispatch_df[
                        (dispatch_df['name'] == gen_name) & 
                        (dispatch_df['DateTime'] == dispatch_hour)
                    ]
                    dispatch = gen_dispatch['value'].sum() if len(gen_dispatch) > 0 else 0.0
                    
                    # Check if binding
                    tolerance = 0.01  # MW
                    is_binding = abs(dispatch - capacity_limit) < tolerance
                    
                    constraints['generators'][gen_name] = {
                        'carrier': gen.get('prime_mover_type', 'unknown'),
                        'base_power': base_power,
                        'rating': rating,
                        'power_factor': power_factor,
                        'max_active_power': max_active_power,
                        'capacity_factor': capacity_factor,
                        'capacity_limit': capacity_limit,
                        'dispatch': dispatch,
                        'is_binding': is_binding,
                        'utilization': dispatch / capacity_limit if capacity_limit > 0 else 0.0,
                    }
                    
                    constraints['total_renewable_dispatch'] += dispatch
                    constraints['total_renewable_capacity'] += capacity_limit
                
                conn.close()
                db_path.unlink()
    
    # Get total load from HDF5 time series (not dispatch CSV which may be wrong)
    # Extract load time series from HDF5
    sienna_loads = [
        c for c in components
        if c.get('__metadata__', {}).get('type') == 'PowerLoad'
    ]
    
    if h5_file.exists() and len(sienna_loads) > 0:
        with h5py.File(h5_file, 'r') as h5:
            if 'time_series_metadata' in h5:
                db_data = h5['time_series_metadata'][()]
                db_path = Path(".temp_load_extraction.db")
                
                with open(db_path, 'wb') as db_file:
                    db_file.write(bytes(db_data))
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                table_name = 'time_series_metadata' if 'time_series_metadata' in tables else 'time_series_associations'
                
                load_uuids = [load.get('internal', {}).get('uuid', {}).get('value') for load in sienna_loads]
                load_uuids = [u for u in load_uuids if u]
                
                if load_uuids:
                    placeholders = ','.join(['?' for _ in load_uuids])
                    query = f'''
                        SELECT owner_uuid, time_series_uuid, initial_timestamp, resolution, length
                        FROM {table_name}
                        WHERE owner_uuid IN ({placeholders}) AND owner_type = 'PowerLoad' AND name = 'max_active_power'
                    '''
                    cursor.execute(query, load_uuids)
                    ts_metadata = cursor.fetchall()
                    
                    total_load = 0.0
                    for load_uuid, ts_uuid, initial_timestamp, resolution, length in ts_metadata:
                        # Read time series data from HDF5
                        possible_paths = [
                            f"/time_series/{ts_uuid}/data",
                            f"/time_series/{ts_uuid}",
                            f"/{ts_uuid}/data",
                        ]
                        
                        ts_data = None
                        for path in possible_paths:
                            if path in h5:
                                if isinstance(h5[path], h5py.Dataset):
                                    ts_data = h5[path][:]
                                    break
                                elif isinstance(h5[path], h5py.Group) and 'data' in h5[path]:
                                    ts_data = h5[path]['data'][:]
                                    break
                        
                        if ts_data is None and 'time_series' in h5:
                            for key in h5['time_series'].keys():
                                if ts_uuid in key or key == ts_uuid:
                                    ts_group = h5['time_series'][key]
                                    if 'data' in ts_group:
                                        ts_data = ts_group['data'][:]
                                        break
                                    elif isinstance(ts_group, h5py.Dataset):
                                        ts_data = ts_group[:]
                                        break
                        
                        if ts_data is not None:
                            # Find index for target hour
                            initial_ts = pd.Timestamp(initial_timestamp)
                            resolution_str = str(resolution)
                            if 'PT' in resolution_str:
                                resolution_str = resolution_str.replace('PT', '')
                                if 'H' in resolution_str:
                                    hours = int(resolution_str.replace('H', ''))
                                    freq = f"{hours}h"
                                else:
                                    freq = "1h"
                            else:
                                freq = "1h"
                            
                            time_index = pd.date_range(start=initial_ts, periods=len(ts_data), freq=freq)
                            
                            # Find closest time
                            time_diffs = pd.Series([abs((ts - dispatch_hour).total_seconds()) for ts in time_index])
                            closest_ts_idx = time_diffs.idxmin()
                            
                            if closest_ts_idx < len(ts_data):
                                # Get load info to convert from per-unit to MW
                                load_info = next((l for l in sienna_loads if l.get('internal', {}).get('uuid', {}).get('value') == load_uuid), None)
                                if load_info:
                                    base_power = load_info.get('base_power', 100.0)
                                    max_active_power_pu = load_info.get('max_active_power', 0.0)
                                    max_active_power_mw = max_active_power_pu * base_power
                                    
                                    # Time series is in per-unit (0-1), convert to MW
                                    load_value = abs(float(ts_data[closest_ts_idx]) * max_active_power_mw)
                                    total_load += load_value
                    
                    constraints['total_load'] = total_load
                    conn.close()
                    db_path.unlink()
    
    # Fallback to dispatch file if HDF5 extraction failed
    if constraints['total_load'] == 0.0:
        load_data = dispatch_df[
            (dispatch_df['carrier'] == 'load') & 
            (dispatch_df['DateTime'] == dispatch_hour)
        ]
        constraints['total_load'] = abs(load_data['value'].sum()) if len(load_data) > 0 else 0.0
    
    return constraints


def compare_constraints_for_hour():
    """Compare constraint values for Jan 3rd evening."""
    
    # Paths
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    json_file = Path("tests/test_output/elec_s380_c7a_ec_lv1_comparison.json")
    h5_file = Path("tests/test_output/elec_s380_c7a_ec_lv1_comparison.h5")
    sienna_dispatch_file = Path("tests/test_output/sienna_dispatch.csv")
    
    logger.info("=" * 80)
    logger.info("CONSTRAINT COMPARISON FOR JAN 3RD EVENING")
    logger.info("=" * 80)
    
    # Load PyPSA network
    network = pypsa.Network(test_file)
    
    # Apply same modifications as in test
    for component in network.components.keys():
        for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
            if attr in network.df(component).columns:
                network.df(component)[attr] = False
    
    network.loads_t.p_set *= 0.75
    
    # Optimize if needed
    if not hasattr(network, 'model') or network.model is None:
        logger.info("Optimizing PyPSA network...")
        network.optimize(
            snapshots=network.snapshots[0:7*24],
            solver_name='gurobi',
            solver_options={
                'OptimalityTol': 1e-9,
                'FeasibilityTol': 1e-9,
                'IntFeasTol': 1e-9,
            }
        )
    
    # Target hour: Jan 3rd evening (6 PM, 7 PM, 8 PM)
    # Adjust year based on your data
    target_hours = [
        pd.Timestamp('2023-01-03 18:00:00'),
        pd.Timestamp('2023-01-03 19:00:00'),
        pd.Timestamp('2023-01-03 20:00:00'),
    ]
    
    # Try to find actual hours in the data
    # Handle both tuple (MultiIndex) and datetime formats
    if len(network.snapshots) > 0:
        if isinstance(network.snapshots[0], tuple):
            # Extract datetime from tuple (usually second element)
            network_snapshots = pd.to_datetime([s[1] if len(s) >= 2 else s[0] for s in network.snapshots])
        else:
            network_snapshots = pd.to_datetime(network.snapshots)
        
        if len(network_snapshots) > 0:
            # Use first snapshot date as reference
            first_date = network_snapshots[0]
            target_hours = [
                first_date.replace(month=1, day=3, hour=18, minute=0, second=0),
                first_date.replace(month=1, day=3, hour=19, minute=0, second=0),
                first_date.replace(month=1, day=3, hour=20, minute=0, second=0),
            ]
    
    for target_hour in target_hours:
        logger.info(f"\n{'='*80}")
        logger.info(f"ANALYZING HOUR: {target_hour}")
        logger.info(f"{'='*80}")
        
        # Extract constraints
        logger.info("\nExtracting PyPSA constraints...")
        pypsa_constraints = extract_pypsa_constraints(network, target_hour)
        
        logger.info("\nExtracting Sienna constraints...")
        sienna_constraints = extract_sienna_constraints(
            json_file, h5_file, sienna_dispatch_file, target_hour
        )
        
        # Compare
        logger.info(f"\n{'='*80}")
        logger.info("COMPARISON SUMMARY")
        logger.info(f"{'='*80}")
        
        logger.info(f"\nTotal Load:")
        logger.info(f"  PyPSA: {pypsa_constraints['total_load']:.2f} MW")
        logger.info(f"  Sienna: {sienna_constraints['total_load']:.2f} MW")
        logger.info(f"  Difference: {abs(pypsa_constraints['total_load'] - sienna_constraints['total_load']):.2f} MW")
        
        logger.info(f"\nTotal Renewable Capacity Available:")
        logger.info(f"  PyPSA: {pypsa_constraints['total_renewable_capacity']:.2f} MW")
        logger.info(f"  Sienna: {sienna_constraints['total_renewable_capacity']:.2f} MW")
        logger.info(f"  Difference: {abs(pypsa_constraints['total_renewable_capacity'] - sienna_constraints['total_renewable_capacity']):.2f} MW")
        
        logger.info(f"\nTotal Renewable Dispatch:")
        logger.info(f"  PyPSA: {pypsa_constraints['total_renewable_dispatch']:.2f} MW")
        logger.info(f"  Sienna: {sienna_constraints['total_renewable_dispatch']:.2f} MW")
        logger.info(f"  Difference: {abs(pypsa_constraints['total_renewable_dispatch'] - sienna_constraints['total_renewable_dispatch']):.2f} MW")
        
        # Compare individual generators
        logger.info(f"\n{'='*80}")
        logger.info("GENERATOR-BY-GENERATOR COMPARISON")
        logger.info(f"{'='*80}")
        
        # Find common generators
        pypsa_gen_names = set(pypsa_constraints['generators'].keys())
        sienna_gen_names = set(sienna_constraints['generators'].keys())
        common_gens = pypsa_gen_names & sienna_gen_names
        
        logger.info(f"\nCommon generators: {len(common_gens)}")
        
        # Compare top generators with differences
        differences = []
        for gen_name in common_gens:
            pypsa_gen = pypsa_constraints['generators'][gen_name]
            sienna_gen = sienna_constraints['generators'][gen_name]
            
            capacity_diff = abs(pypsa_gen['capacity_limit'] - sienna_gen['capacity_limit'])
            dispatch_diff = abs(pypsa_gen['dispatch'] - sienna_gen['dispatch'])
            
            differences.append({
                'name': gen_name,
                'carrier': pypsa_gen['carrier'],
                'pypsa_capacity': pypsa_gen['capacity_limit'],
                'sienna_capacity': sienna_gen['capacity_limit'],
                'capacity_diff': capacity_diff,
                'pypsa_dispatch': pypsa_gen['dispatch'],
                'sienna_dispatch': sienna_gen['dispatch'],
                'dispatch_diff': dispatch_diff,
                'pypsa_binding': pypsa_gen['is_binding'],
                'sienna_binding': sienna_gen['is_binding'],
            })
        
        # Sort by dispatch difference
        differences_sorted = sorted(differences, key=lambda x: x['dispatch_diff'], reverse=True)
        
        logger.info(f"\nTop 20 generators by dispatch difference:")
        logger.info(f"{'Name':<35} {'Carrier':<10} {'PyPSA Cap':<12} {'Sienna Cap':<12} {'Cap Diff':<12} {'PyPSA Disp':<12} {'Sienna Disp':<12} {'Disp Diff':<12} {'PyPSA Bind':<12} {'Sienna Bind':<12}")
        logger.info("-" * 140)
        
        for d in differences_sorted[:20]:
            logger.info(
                f"{d['name']:<35} {d['carrier']:<10} "
                f"{d['pypsa_capacity']:>11.2f} {d['sienna_capacity']:>11.2f} "
                f"{d['capacity_diff']:>11.2f} {d['pypsa_dispatch']:>11.2f} "
                f"{d['sienna_dispatch']:>11.2f} {d['dispatch_diff']:>11.2f} "
                f"{str(d['pypsa_binding']):<12} {str(d['sienna_binding']):<12}"
            )
        
        # Count binding constraints
        pypsa_binding = sum(1 for g in pypsa_constraints['generators'].values() if g['is_binding'])
        sienna_binding = sum(1 for g in sienna_constraints['generators'].values() if g['is_binding'])
        
        logger.info(f"\nBinding constraints (dispatch at capacity limit):")
        logger.info(f"  PyPSA: {pypsa_binding}/{len(pypsa_constraints['generators'])}")
        logger.info(f"  Sienna: {sienna_binding}/{len(sienna_constraints['generators'])}")
        
        # Find generators binding in one but not the other
        binding_mismatches = []
        for gen_name in common_gens:
            pypsa_gen = pypsa_constraints['generators'][gen_name]
            sienna_gen = sienna_constraints['generators'][gen_name]
            
            if pypsa_gen['is_binding'] != sienna_gen['is_binding']:
                binding_mismatches.append({
                    'name': gen_name,
                    'carrier': pypsa_gen['carrier'],
                    'pypsa_binding': pypsa_gen['is_binding'],
                    'sienna_binding': sienna_gen['is_binding'],
                    'pypsa_dispatch': pypsa_gen['dispatch'],
                    'sienna_dispatch': sienna_gen['dispatch'],
                    'pypsa_capacity': pypsa_gen['capacity_limit'],
                    'sienna_capacity': sienna_gen['capacity_limit'],
                })
        
        if binding_mismatches:
            logger.warning(f"\n⚠️  Generators with binding constraint mismatches: {len(binding_mismatches)}")
            logger.info(f"{'Name':<35} {'Carrier':<10} {'PyPSA Bind':<12} {'Sienna Bind':<12} {'PyPSA Disp':<12} {'Sienna Disp':<12} {'PyPSA Cap':<12} {'Sienna Cap':<12}")
            logger.info("-" * 120)
            for m in binding_mismatches[:20]:
                logger.warning(
                    f"{m['name']:<35} {m['carrier']:<10} "
                    f"{str(m['pypsa_binding']):<12} {str(m['sienna_binding']):<12} "
                    f"{m['pypsa_dispatch']:>11.2f} {m['sienna_dispatch']:>11.2f} "
                    f"{m['pypsa_capacity']:>11.2f} {m['sienna_capacity']:>11.2f}"
                )
        
        # Check for partial curtailment in PyPSA
        logger.info(f"\n{'='*80}")
        logger.info("PARTIAL CURTAILMENT CHECK (PyPSA)")
        logger.info(f"{'='*80}")
        logger.info("Checking if PyPSA allows partial curtailment (dispatch != capacity_limit AND dispatch != 0)")
        
        tolerance = 0.01  # MW
        partial_curtailment_cases = []
        
        for gen_name, gen_data in pypsa_constraints['generators'].items():
            dispatch = gen_data['dispatch']
            capacity_limit = gen_data['capacity_limit']
            
            # Partial curtailment: dispatch is between 0 and capacity_limit (not at either bound)
            if dispatch > tolerance and dispatch < (capacity_limit - tolerance):
                partial_curtailment_cases.append({
                    'name': gen_name,
                    'carrier': gen_data['carrier'],
                    'dispatch': dispatch,
                    'capacity_limit': capacity_limit,
                    'curtailment': capacity_limit - dispatch,
                    'curtailment_pct': (capacity_limit - dispatch) / capacity_limit * 100 if capacity_limit > 0 else 0.0,
                })
        
        if partial_curtailment_cases:
            logger.warning(f"\n⚠️  Found {len(partial_curtailment_cases)} PyPSA generators with partial curtailment:")
            logger.info(f"{'Name':<35} {'Carrier':<10} {'Dispatch':<12} {'Capacity Limit':<15} {'Curtailment':<12} {'Curtailment %':<12}")
            logger.info("-" * 100)
            # Sort by curtailment amount
            sorted_cases = sorted(partial_curtailment_cases, key=lambda x: x['curtailment'], reverse=True)
            for case in sorted_cases[:20]:  # Show top 20
                logger.warning(
                    f"{case['name']:<35} {case['carrier']:<10} "
                    f"{case['dispatch']:>11.2f} {case['capacity_limit']:>14.2f} "
                    f"{case['curtailment']:>11.2f} {case['curtailment_pct']:>11.2f}%"
                )
        else:
            logger.info(f"\n✓ No partial curtailment found in PyPSA for this hour.")
            logger.info("  All generators are either at capacity limit or at zero dispatch.")


if __name__ == "__main__":
    compare_constraints_for_hour()

