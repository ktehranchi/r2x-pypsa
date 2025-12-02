"""Helper functions for testing PyPSA to Sienna conversion."""

import json
import h5py
import sqlite3
import tempfile
import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Union
from r2x.api import System


def get_sienna_capacity_factors(
    json_file_or_system: Union[Path, str, System],
    generator_name: str,
    time_index: Optional[pd.DatetimeIndex] = None,
    h5_file: Optional[Union[Path, str]] = None,
) -> pd.Series:
    """Get capacity factors using System API if available, otherwise fall back to file-based approach."""
    # Try System API first if a System object is provided
    if isinstance(json_file_or_system, System):
        try:
            from r2x.models import RenewableDispatch
            
            # Try to get the generator
            gen = json_file_or_system.get_component(RenewableDispatch, generator_name)
            if gen:
                # Get time series
                ts_list = list(json_file_or_system.list_time_series(gen))
                max_power_ts = None
                for ts in ts_list:
                    if ts.name == "max_active_power":
                        max_power_ts = ts
                        break
                
                if max_power_ts:
                    # Convert to Series
                    ts_data = max_power_ts.data
                    if hasattr(ts_data, 'index'):
                        ts_series = ts_data
                    else:
                        # Create index if needed
                        if time_index is not None:
                            ts_series = pd.Series(ts_data, index=time_index)
                        else:
                            # Try to get from time series metadata
                            initial_ts = pd.Timestamp("2030-01-01")
                            ts_series = pd.Series(ts_data, index=pd.date_range(start=initial_ts, periods=len(ts_data), freq="h"))
                    
                    if time_index is not None:
                        ts_series = ts_series.reindex(time_index, method='nearest')
                    
                    return ts_series
        except Exception:
            # Fall through to file-based approach
            pass
    
    # Fall back to file-based approach
    return _get_sienna_capacity_factors_from_files(
        json_file_or_system, generator_name, time_index, h5_file
    )


def _get_sienna_capacity_factors_from_files(
    json_file: Union[Path, str],
    generator_name: str,
    time_index: Optional[pd.DatetimeIndex] = None,
    h5_file: Optional[Union[Path, str]] = None,
) -> pd.Series:
    """Get capacity factors from files (internal helper).
    
    This function reads directly from JSON and H5 files.
    Note: Time series metadata may not be in JSON - this is a known limitation.
    Consider using System API instead if components are accessible.
    """
    json_file = Path(json_file)
    
    # Infer H5 file path from JSON file if not provided
    if h5_file is None:
        h5_file = json_file.with_suffix('.h5')
        # Try alternative naming (with _optimized suffix)
        if not h5_file.exists() and '_optimized' in json_file.stem:
            h5_file = json_file.parent / f"{json_file.stem}.h5"
        elif not h5_file.exists():
            # Try adding _optimized
            h5_file = json_file.parent / f"{json_file.stem}_optimized.h5"
    else:
        h5_file = Path(h5_file)
    
    if not json_file.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file}")
    if not h5_file.exists():
        raise FileNotFoundError(f"H5 file not found: {h5_file}")
    
    # Load JSON
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Find generator
    gen_data = None
    gen_uuid = None
    
    for component in data['data']['components']:
        if component.get('name') == generator_name:
            gen_data = component
            gen_uuid = component.get('internal', {}).get('uuid', {}).get('value')
            break
    
    if gen_data is None:
        raise ValueError(f"Generator '{generator_name}' not found in JSON file")
    
    if not gen_uuid:
        raise ValueError(f"Generator '{generator_name}' has no UUID")
    
    # Find time series UUID using SQLite metadata database in H5 file
    ts_uuid = None
    ts_meta = None
    
    # Read SQLite database from H5 file
    with h5py.File(h5_file, 'r') as h5:
        if 'time_series_metadata' not in h5:
            raise ValueError(f"No time_series_metadata found in H5 file: {h5_file}")
        
        metadata_bytes = bytes(h5['time_series_metadata'][:])
        
        # Write to temporary file to query SQLite
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            tmp_file.write(metadata_bytes)
            tmp_db_path = tmp_file.name
        
        try:
            # Query SQLite database
            db_conn = sqlite3.connect(tmp_db_path)
            cursor = db_conn.cursor()
            
            # Query for max_active_power time series for this component
            cursor.execute(
                'SELECT time_series_uuid, initial_timestamp, resolution, length '
                'FROM time_series_associations '
                'WHERE owner_uuid = ? AND name = ?',
                (gen_uuid, 'max_active_power')
            )
            result = cursor.fetchone()
            
            if result:
                ts_uuid, initial_timestamp, resolution, length = result
                ts_meta = {
                    'uuid': {'value': ts_uuid},
                    'name': 'max_active_power',
                    'initial_timestamp': initial_timestamp,
                    'resolution': resolution,
                    'count': length,
                }
            else:
                # Check what time series exist for this component
                cursor.execute(
                    'SELECT name FROM time_series_associations WHERE owner_uuid = ?',
                    (gen_uuid,)
                )
                available_names = [row[0] for row in cursor.fetchall()]
                
                db_conn.close()
                raise ValueError(
                    f"Time series 'max_active_power' not found for generator '{generator_name}' (UUID: {gen_uuid}). "
                    f"Available time series for this component: {available_names}"
                )
            
            db_conn.close()
        finally:
            os.unlink(tmp_db_path)
    
    # Read time series data from H5 file
    with h5py.File(h5_file, 'r') as h5:
        # Try different possible paths
        possible_paths = [
            f"/time_series/{ts_uuid}/data",
            f"/time_series/{ts_uuid}",
            f"/{ts_uuid}/data",
        ]
        
        ts_data = None
        used_path = None
        
        for path in possible_paths:
            if path in h5:
                if isinstance(h5[path], h5py.Dataset):
                    ts_data = h5[path][:]
                    used_path = path
                    break
                elif isinstance(h5[path], h5py.Group) and 'data' in h5[path]:
                    ts_data = h5[path]['data'][:]
                    used_path = f"{path}/data"
                    break
        
        # If not found, try searching by UUID in time_series group
        if ts_data is None and 'time_series' in h5:
            for key in h5['time_series'].keys():
                if ts_uuid in key or key == ts_uuid:
                    ts_group = h5['time_series'][key]
                    if 'data' in ts_group:
                        ts_data = ts_group['data'][:]
                        used_path = f"/time_series/{key}/data"
                        break
                    elif isinstance(ts_group, h5py.Dataset):
                        ts_data = ts_group[:]
                        used_path = f"/time_series/{key}"
                        break
        
        if ts_data is None:
            raise ValueError(
                f"Time series data not found in H5 file for UUID {ts_uuid}. "
                f"Available paths in /time_series: {list(h5.get('time_series', {}).keys())[:10]}"
            )
    
    # Create time index
    initial_ts = pd.Timestamp(ts_meta.get('initial_timestamp'))
    
    # Parse resolution (e.g., "PT1H" = 1 hour, "PT15M" = 15 minutes)
    resolution_str = str(ts_meta.get('resolution', 'PT1H'))
    if 'PT' in resolution_str:
        # Remove 'PT' prefix
        resolution_str = resolution_str.replace('PT', '')
        if 'H' in resolution_str:
            hours = int(resolution_str.replace('H', ''))
            freq = f"{hours}h"
        elif 'M' in resolution_str:
            minutes = int(resolution_str.replace('M', ''))
            freq = f"{minutes}min"
        elif 'S' in resolution_str:
            seconds = int(resolution_str.replace('S', ''))
            freq = f"{seconds}s"
        else:
            freq = "1h"  # default
    else:
        freq = "1h"  # default
    
    # Create full time index
    full_time_index = pd.date_range(start=initial_ts, periods=len(ts_data), freq=freq)
    
    # Create Series
    ts_series = pd.Series(ts_data, index=full_time_index, name='capacity_factor')
    
    # Extract specific time index if requested
    if time_index is not None:
        # Find matching times
        if isinstance(time_index, pd.DatetimeIndex):
            # Use reindex to align, forward-fill if needed
            ts_series = ts_series.reindex(time_index, method='nearest')
        else:
            # Single timestamp
            if time_index in ts_series.index:
                ts_series = ts_series.loc[[time_index]]
            else:
                # Find nearest
                closest_idx = ts_series.index.get_indexer([time_index], method='nearest')[0]
                closest_time = ts_series.index[closest_idx]
                ts_series = ts_series.loc[[closest_time]]
                ts_series.index = [time_index]  # Use requested time
    
    return ts_series


def get_sienna_generator_info(
    json_file: Path | str,
    generator_name: str,
) -> dict:
    """Get generator information from Sienna JSON file.
    
    Parameters
    ----------
    json_file : Path | str
        Path to Sienna JSON file
    generator_name : str
        Name of the generator
        
    Returns
    -------
    dict
        Dictionary with generator properties (base_power, rating, power_factor, etc.)
    """
    json_file = Path(json_file)
    
    if not json_file.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file}")
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Find generator
    gen_data = None
    for component in data['data']['components']:
        if component.get('name') == generator_name:
            gen_data = component
            break
    
    if gen_data is None:
        raise ValueError(f"Generator '{generator_name}' not found in JSON file")
    
    # Extract relevant properties
    base_power = gen_data.get('base_power', 0.0)
    rating = gen_data.get('rating', 1.0)
    power_factor = gen_data.get('power_factor', 1.0)
    max_capacity = rating * power_factor * base_power
    
    return {
        'name': gen_data.get('name'),
        'type': gen_data.get('__metadata__', {}).get('type'),
        'uuid': gen_data.get('internal', {}).get('uuid', {}).get('value'),
        'base_power': base_power,
        'rating': rating,
        'power_factor': power_factor,
        'max_capacity': max_capacity,
        'prime_mover_type': gen_data.get('prime_mover_type'),
    }

