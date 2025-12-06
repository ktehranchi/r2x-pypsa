"""Helper functions for comparing time series between PyPSA and Sienna systems."""

import pandas as pd
import h5py
import sqlite3
from pathlib import Path
from loguru import logger
from typing import Optional, Callable, Tuple, List


def extract_pypsa_generator_time_series(
    network,
    carriers: List[str],
    generator_filter: Optional[Callable] = None
) -> Tuple[Optional[pd.Series], int, float]:
    """
    Extract capacity-weighted time series for PyPSA generators by carrier type(s).
    
    Parameters
    ----------
    network : pypsa.Network
        PyPSA network object
    carriers : List[str]
        List of carrier strings (e.g., ['solar'], ['onwind', 'offwind', 'wind'])
    generator_filter : Optional[Callable]
        Optional function to filter generators (e.g., lambda df: df.p_nom > 0)
    
    Returns
    -------
    Tuple[Optional[pd.Series], int, float]
        - total_ts: pandas Series with capacity-weighted total generation (MW) at each timestep, or None if no data
        - count: Number of generators found
        - total_capacity: Total capacity in MW
    """
    # Filter generators by carrier
    generators = network.generators[network.generators.carrier.isin(carriers)]
    
    # Apply additional filter if provided
    if generator_filter is not None:
        generators = generators[generator_filter(generators)]
    
    count = len(generators)
    
    if count == 0:
        return None, 0, 0.0
    
    # Calculate total capacity
    total_capacity = generators.p_nom.sum()
    
    # Extract time series if available
    total_ts = None
    if hasattr(network.generators_t, 'p_max_pu'):
        # Get generator names
        gen_names = generators.index.tolist()
        
        # Check if all generators have time series
        if all(name in network.generators_t.p_max_pu.columns for name in gen_names):
            # Get capacity factors time series (per-unit)
            cf_ts = network.generators_t.p_max_pu[gen_names]
            
            # Get p_nom for each generator (for capacity weighting)
            p_nom = generators.p_nom
            
            # Calculate total generation potential at each timestep: sum(capacity_factor × p_nom)
            # This gives total MW available from all generators
            total_ts = pd.Series(0.0, index=cf_ts.index)
            for name in gen_names:
                if name in cf_ts.columns:
                    cf_ts_single = cf_ts[name]
                    p_nom_single = p_nom.loc[name]
                    # Capacity-weighted: capacity_factor × p_nom (gives MW)
                    total_ts += cf_ts_single * p_nom_single
        else:
            logger.warning(f"Some PyPSA generators with carriers {carriers} missing p_max_pu time series")
    
    return total_ts, count, total_capacity


def extract_sienna_generator_time_series(
    json_file: Path,
    h5_file: Path,
    prime_mover_types: List[str],
    output_dir: Path,
    component_type: str = 'RenewableDispatch'
) -> Tuple[Optional[pd.Series], int, float, int]:
    """
    Extract capacity-weighted time series for Sienna generators by prime_mover_type(s).
    
    Parameters
    ----------
    json_file : Path
        Path to Sienna JSON file
    h5_file : Path
        Path to Sienna HDF5 file
    prime_mover_types : List[str]
        List of prime mover type strings (e.g., ['PVe'], ['WT', 'WS'])
    output_dir : Path
        Directory for temporary files
    component_type : str
        Component type to filter (default: 'RenewableDispatch')
    
    Returns
    -------
    Tuple[Optional[pd.Series], int, float, int]
        - total_ts: pandas Series with capacity-weighted total generation (MW) at each timestep, or None if no data
        - count: Number of generators found
        - total_capacity: Total capacity in MW
        - with_ts_count: Number of generators with time series
    """
    import json
    
    # Load JSON to find generators
    with open(json_file) as f:
        sienna_data = json.load(f)
    
    components = sienna_data.get('data', {}).get('components', [])
    
    # Filter generators by prime_mover_type
    generators = [
        c for c in components
        if c.get('__metadata__', {}).get('type') == component_type
        and c.get('prime_mover_type') in prime_mover_types
    ]
    
    count = len(generators)
    with_ts_count = 0
    # Calculate total capacity using max_active_power = rating * base_power * power_factor
    # With the new system: base_power = 100.0 (system-wide), rating = p_nom / 100.0 (per-unit)
    # So max_active_power = (p_nom / 100.0) * 100.0 * 1.0 = p_nom MW
    total_capacity = sum(
        g.get('rating', 0.0) * g.get('base_power', 0.0) * g.get('power_factor', 1.0)
        for g in generators
    )
    total_ts = None
    
    if count == 0 or not h5_file.exists():
        return None, count, total_capacity, 0
    
    # Extract time series from HDF5
    with h5py.File(h5_file, 'r') as h5:
        if 'time_series_metadata' not in h5:
            logger.warning(f"No 'time_series_metadata' found in H5 file for prime_mover_types {prime_mover_types}")
            return None, count, total_capacity, 0
        
        db_data = h5['time_series_metadata'][()]
        db_path = output_dir / f".temp_metadata_{'_'.join(prime_mover_types)}.db"
        
        with open(db_path, 'wb') as db_file:
            db_file.write(bytes(db_data))
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check what tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        table_name = 'time_series_metadata' if 'time_series_metadata' in tables else 'time_series_associations'
        
        # Get generator UUIDs
        gen_uuids = [g.get('internal', {}).get('uuid', {}).get('value') for g in generators]
        gen_uuids = [u for u in gen_uuids if u]  # Filter out None values
        
        if not gen_uuids:
            conn.close()
            db_path.unlink()
            return None, count, total_capacity, 0
        
        # Count generators with time series
        placeholders = ','.join(['?' for _ in gen_uuids])
        query = f'''
            SELECT COUNT(DISTINCT owner_uuid)
            FROM {table_name}
            WHERE owner_uuid IN ({placeholders}) AND owner_type = ? AND name = 'max_active_power'
        '''
        cursor.execute(query, gen_uuids + [component_type])
        with_ts_count = cursor.fetchone()[0]
        
        # Extract time series for each generator
        if with_ts_count > 0:
            query = f'''
                SELECT owner_uuid, time_series_uuid, initial_timestamp, resolution, length
                FROM {table_name}
                WHERE owner_uuid IN ({placeholders}) AND owner_type = ? AND name = 'max_active_power'
            '''
            cursor.execute(query, gen_uuids + [component_type])
            ts_metadata = cursor.fetchall()
            
            # Store generator time series (per-generator, will sum later)
            gen_time_series = {}  # {gen_uuid: pd.Series}
            
            for gen_uuid, ts_uuid, initial_timestamp, resolution, length in ts_metadata:
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
                
                # If not found, search in time_series group
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
                    # Create time index
                    initial_ts = pd.Timestamp(initial_timestamp)
                    
                    # Parse resolution
                    resolution_str = str(resolution)
                    if 'PT' in resolution_str:
                        resolution_str = resolution_str.replace('PT', '')
                        if 'H' in resolution_str:
                            hours = int(resolution_str.replace('H', ''))
                            freq = f"{hours}h"
                        elif 'M' in resolution_str:
                            minutes = int(resolution_str.replace('M', ''))
                            freq = f"{minutes}min"
                        else:
                            freq = "1h"
                    else:
                        freq = "1h"
                    
                    # Create time index
                    time_index = pd.date_range(start=initial_ts, periods=len(ts_data), freq=freq)
                    
                    # Get generator info to convert from per-unit to MW
                    gen_info = next(
                        (g for g in generators if g.get('internal', {}).get('uuid', {}).get('value') == gen_uuid),
                        None
                    )
                    if gen_info:
                        base_power = gen_info.get('base_power', 0.0)
                        rating = gen_info.get('rating', 0.0)
                        power_factor = gen_info.get('power_factor', 1.0)
                        
                        # Calculate max_active_power = rating * base_power * power_factor
                        # Time series is in per-unit (0-1), convert to MW: ts_pu * max_active_power
                        max_active_power = rating * base_power * power_factor
                        ts_mw = pd.Series(ts_data * max_active_power, index=time_index)
                        gen_time_series[gen_uuid] = ts_mw
            
            # Sum all generator time series to get total generation at each timestep
            if gen_time_series:
                # Align all series to common time index (use union of all indices)
                all_indices = set()
                for ts in gen_time_series.values():
                    all_indices.update(ts.index)
                common_index = pd.DatetimeIndex(sorted(all_indices))
                
                # Reindex and sum
                total_series = pd.Series(0.0, index=common_index)
                for ts in gen_time_series.values():
                    ts_aligned = ts.reindex(common_index, fill_value=0.0)
                    total_series += ts_aligned
                
                total_ts = total_series
        
        conn.close()
        db_path.unlink()
    
    return total_ts, count, total_capacity, with_ts_count


def compare_time_series(
    pypsa_ts: Optional[pd.Series],
    sienna_ts: Optional[pd.Series],
    tolerance_mw: float = 0.01,
    min_timesteps: int = 20,
    name: str = "Time series"
) -> Tuple[bool, int, int, float, float]:
    """
    Compare two time series by index position (handles timestamp format differences).
    
    Parameters
    ----------
    pypsa_ts : Optional[pd.Series]
        PyPSA time series (pandas Series)
    sienna_ts : Optional[pd.Series]
        Sienna time series (pandas Series)
    tolerance_mw : float
        Tolerance in MW (default 0.01)
    min_timesteps : int
        Minimum number of timesteps to check (default 20)
    name : str
        Name for logging (default "Time series")
    
    Returns
    -------
    Tuple[bool, int, int, float, float]
        - match: Boolean indicating if all timesteps match within tolerance
        - match_count: Number of matching timesteps
        - total_count: Total number of timesteps checked
        - max_diff: Maximum difference in MW
        - mean_diff: Mean difference in MW
    """
    if pypsa_ts is None or sienna_ts is None:
        return False, 0, 0, 0.0, 0.0
    
    # Align by index position instead of timestamps (handles T vs space format differences)
    min_length = min(len(pypsa_ts), len(sienna_ts))
    
    if min_length == 0:
        return False, 0, 0, 0.0, 0.0
    
    # Extract values by position (ignore timestamp format differences)
    pypsa_values = pypsa_ts.values[:min_length]
    sienna_values = sienna_ts.values[:min_length]
    
    # Compare at least min_timesteps (or all available if fewer)
    num_timesteps_to_check = min_length
    if num_timesteps_to_check < min_timesteps:
        logger.warning(f"Only {num_timesteps_to_check} timesteps available (less than {min_timesteps} requested) for {name}")
    
    # Log summary statistics
    pypsa_min = float(pypsa_values.min()) if len(pypsa_values) > 0 else 0.0
    pypsa_max = float(pypsa_values.max()) if len(pypsa_values) > 0 else 0.0
    pypsa_mean = float(pypsa_values.mean()) if len(pypsa_values) > 0 else 0.0
    sienna_min = float(sienna_values.min()) if len(sienna_values) > 0 else 0.0
    sienna_max = float(sienna_values.max()) if len(sienna_values) > 0 else 0.0
    sienna_mean = float(sienna_values.mean()) if len(sienna_values) > 0 else 0.0
    
    logger.info(f"{name} comparison: Checking {num_timesteps_to_check} timesteps")
    logger.info(f"  PyPSA range: [{pypsa_min:.2f}, {pypsa_max:.2f}] MW, mean: {pypsa_mean:.2f} MW")
    logger.info(f"  Sienna range: [{sienna_min:.2f}, {sienna_max:.2f}] MW, mean: {sienna_mean:.2f} MW")
    
    differences = []
    matches = 0
    
    # Determine sample indices to log (first 3, middle 1, last 3)
    sample_indices = []
    if num_timesteps_to_check > 0:
        # First 3
        sample_indices.extend(range(min(3, num_timesteps_to_check)))
        # Middle 1
        if num_timesteps_to_check > 6:
            middle_idx = num_timesteps_to_check // 2
            if middle_idx not in sample_indices:
                sample_indices.append(middle_idx)
        # Last 3
        if num_timesteps_to_check > 3:
            last_start = max(3, num_timesteps_to_check - 3)
            for idx in range(last_start, num_timesteps_to_check):
                if idx not in sample_indices:
                    sample_indices.append(idx)
    
    # Sort sample indices
    sample_indices = sorted(set(sample_indices))
    
    for i in range(num_timesteps_to_check):
        pypsa_val = pypsa_values[i]
        sienna_val = sienna_values[i]
        diff = abs(pypsa_val - sienna_val)
        differences.append(diff)
        
        if diff <= tolerance_mw:
            matches += 1
        else:
            # Get timestamp for logging (use PyPSA index if available)
            ts_str = str(pypsa_ts.index[i]) if i < len(pypsa_ts.index) else f"index_{i}"
            logger.debug(f"{name} mismatch at {ts_str}: PyPSA={pypsa_val:.4f} MW, Sienna={sienna_val:.4f} MW, diff={diff:.4f} MW")
        
        # Log sample timesteps (both matches and mismatches) at INFO level
        if i in sample_indices:
            ts_str = str(pypsa_ts.index[i]) if i < len(pypsa_ts.index) else f"index_{i}"
            match_status = "✓" if diff <= tolerance_mw else "✗"
            logger.info(f"  {match_status} Sample timestep {i} ({ts_str}): PyPSA={pypsa_val:.4f} MW, Sienna={sienna_val:.4f} MW, diff={diff:.6f} MW")
    
    match = matches == num_timesteps_to_check
    max_diff = max(differences) if differences else 0.0
    mean_diff = sum(differences) / len(differences) if differences else 0.0
    
    logger.info(f"{name} comparison summary: {matches}/{num_timesteps_to_check} timesteps match (tolerance: {tolerance_mw} MW)")
    logger.info(f"  Max difference: {max_diff:.6f} MW, Mean difference: {mean_diff:.6f} MW")
    
    return match, matches, num_timesteps_to_check, max_diff, mean_diff

