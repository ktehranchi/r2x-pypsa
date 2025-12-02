#!/usr/bin/env python3
"""
Get solar capacity factors or output power for a specific generator at a specific time.
Reads directly from JSON and H5 files.
"""

import json
import h5py
import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger

# File paths
H5_FILE = Path("/Users/henrydaniels-koch/Documents/Stanford_Grad_School/INES_Research/r2x-pypsa/tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.h5")
JSON_FILE = Path("/Users/henrydaniels-koch/Documents/Stanford_Grad_School/INES_Research/r2x-pypsa/tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json")

# Generator name and time
GEN_NAME = "p600 0 solar existing"
TARGET_TIME = pd.Timestamp("2030-01-01 00:00:00")

def find_generator_in_json(gen_name):
    """Find generator in JSON file."""
    with open(JSON_FILE) as f:
        data = json.load(f)
    
    # Search for the generator
    for component in data['data']['components']:
        if component.get('name') == gen_name:
            return component
    
    # Try case-insensitive search
    for component in data['data']['components']:
        if component.get('name', '').lower() == gen_name.lower():
            logger.info(f"Found generator with case-insensitive match: {component.get('name')}")
            return component
    
    # Try partial match
    for component in data['data']['components']:
        name = component.get('name', '')
        if 'p600' in name.lower() and 'solar' in name.lower() and 'existing' in name.lower():
            logger.info(f"Found generator with partial match: {name}")
            return component
    
    return None

def get_time_series_from_h5(gen_uuid, target_time):
    """Get time series data from H5 file for a specific generator UUID."""
    with h5py.File(H5_FILE, 'r') as f:
        # H5 file structure for time series
        # Time series are stored under a root path, typically with UUIDs
        
        # Try to find the time series for this UUID
        # The structure might be: /time_series/<uuid>/data
        # or similar
        
        logger.info(f"Searching for time series with UUID: {gen_uuid}")
        
        # List all groups/keys in the H5 file
        def print_structure(name, obj):
            if isinstance(obj, h5py.Dataset):
                logger.debug(f"  Dataset: {name}, shape: {obj.shape}, dtype: {obj.dtype}")
            elif isinstance(obj, h5py.Group):
                logger.debug(f"  Group: {name}")
        
        # Try common paths
        possible_paths = [
            '/time_series',
            '/timeseries',
            '/data',
            '/',
        ]
        
        for path in possible_paths:
            if path in f:
                logger.info(f"Found path: {path}")
                # Try to find UUID
                if isinstance(f[path], h5py.Group):
                    for key in f[path].keys():
                        if gen_uuid in key or key == gen_uuid:
                            logger.info(f"Found potential match: {key}")
                            try:
                                ts_group = f[path][key]
                                if 'data' in ts_group:
                                    data = ts_group['data'][:]
                                    logger.info(f"Found data array with shape: {data.shape}")
                                    
                                    # Try to get metadata for time index
                                    if 'initial_timestamp' in ts_group.attrs:
                                        initial_ts = pd.Timestamp(ts_group.attrs['initial_timestamp'])
                                        logger.info(f"Initial timestamp: {initial_ts}")
                                    
                                    if 'resolution' in ts_group.attrs:
                                        resolution = ts_group.attrs['resolution']
                                        logger.info(f"Resolution: {resolution}")
                                    
                                    return data, initial_ts if 'initial_ts' in locals() else None, resolution if 'resolution' in locals() else None
                            except Exception as e:
                                logger.warning(f"Error reading {key}: {e}")
        
        # If we can't find it, return None
        logger.warning("Could not find time series data in H5 file")
        return None, None, None

def main():
    """Main function."""
    logger.info(f"Looking for generator: {GEN_NAME}")
    logger.info(f"Target time: {TARGET_TIME}")
    
    # Find generator in JSON
    gen_data = find_generator_in_json(GEN_NAME)
    
    if gen_data is None:
        logger.error(f"Generator '{GEN_NAME}' not found in JSON file!")
        return
    
    logger.info(f"Found generator: {gen_data['name']}")
    logger.info(f"  Type: {gen_data.get('__metadata__', {}).get('type')}")
    logger.info(f"  Prime mover: {gen_data.get('prime_mover_type')}")
    logger.info(f"  Base power: {gen_data.get('base_power')} MW")
    logger.info(f"  Rating: {gen_data.get('rating')}")
    logger.info(f"  Power factor: {gen_data.get('power_factor')}")
    
    # Calculate max capacity
    base_power = gen_data.get('base_power', 0.0)
    rating = gen_data.get('rating', 1.0)
    power_factor = gen_data.get('power_factor', 1.0)
    max_capacity = rating * power_factor * base_power
    
    logger.info(f"  Max capacity: {max_capacity} MW")
    
    # Get UUID
    gen_uuid = gen_data.get('internal', {}).get('uuid', {}).get('value')
    if not gen_uuid:
        logger.error("Could not find UUID for generator")
        return
    
    logger.info(f"  UUID: {gen_uuid}")
    
    # Try to get time series from H5
    ts_data, initial_ts, resolution = get_time_series_from_h5(gen_uuid, TARGET_TIME)
    
    if ts_data is None:
        logger.warning("Could not read time series from H5 file directly")
        logger.info("Trying alternative approach: use System API")
        
        # Fallback: try using System API
        try:
            from r2x.api import System
            from r2x.models import RenewableDispatch
            from infrasys.component import Component
            
            sys = System(str(JSON_FILE))
            
            # Try multiple methods to find the generator
            gen = None
            
            # Method 1: get_components
            try:
                all_renewable = list(sys.get_components(RenewableDispatch))
                logger.info(f"Found {len(all_renewable)} generators via get_components()")
                for g in all_renewable:
                    if g.name == gen_data['name']:
                        gen = g
                        break
            except Exception as e:
                logger.warning(f"get_components() failed: {e}")
            
            # Method 2: _component_mgr.iter_all()
            if gen is None:
                try:
                    all_components = list(sys._component_mgr.iter_all())
                    logger.info(f"Found {len(all_components)} components via _component_mgr")
                    for comp in all_components:
                        if isinstance(comp, RenewableDispatch) and comp.name == gen_data['name']:
                            gen = comp
                            break
                except Exception as e:
                    logger.warning(f"_component_mgr.iter_all() failed: {e}")
            
            # Method 3: get_component by name
            if gen is None:
                try:
                    gen = sys.get_component(RenewableDispatch, gen_data['name'])
                    logger.info("Found generator via get_component()")
                except Exception as e:
                    logger.warning(f"get_component() failed: {e}")
            
            if gen:
                logger.info("Found generator via System API")
                time_series_list = list(sys.list_time_series(gen))
                logger.info(f"Time series available: {[ts.name for ts in time_series_list]}")
                
                for ts in time_series_list:
                    if ts.name == "max_active_power":
                        ts_data_obj = ts.data
                        logger.info(f"Time series data type: {type(ts_data_obj)}")
                        
                        # Try to convert to array
                        if hasattr(ts_data_obj, '__array__'):
                            ts_data = np.array(ts_data_obj)
                        elif hasattr(ts_data_obj, 'values'):
                            ts_data = ts_data_obj.values
                        else:
                            ts_data = list(ts_data_obj)
                        
                        logger.info(f"Time series shape: {len(ts_data)}")
                        
                        # Try to get time index
                        if hasattr(ts, 'time_index'):
                            time_index = ts.time_index
                        elif hasattr(sys, 'get_time_series_index'):
                            time_index = sys.get_time_series_index(gen, "max_active_power")
                        else:
                            # Assume hourly starting from 2030-01-01
                            time_index = pd.date_range(start="2030-01-01", periods=len(ts_data), freq="h")
                        
                        # Create Series
                        ts_series = pd.Series(ts_data, index=time_index)
                        
                        # Get value at target time
                        if TARGET_TIME in ts_series.index:
                            capacity_factor = ts_series.loc[TARGET_TIME]
                        else:
                            closest_idx = ts_series.index.get_indexer([TARGET_TIME], method='nearest')[0]
                            closest_time = ts_series.index[closest_idx]
                            capacity_factor = ts_series.loc[closest_time]
                            logger.warning(f"Exact time not found, using closest: {closest_time}")
                        
                        available_power = capacity_factor * max_capacity
                        
                        print(f"\n{'='*60}")
                        print(f"Results for {gen_data['name']} at {TARGET_TIME}")
                        print(f"{'='*60}")
                        print(f"Capacity factor (per-unit): {capacity_factor:.6f}")
                        print(f"Max capacity: {max_capacity:.6f} MW")
                        print(f"Available power: {available_power:.6f} MW")
                        print(f"{'='*60}\n")
                        return
        except Exception as e:
            logger.error(f"System API approach failed: {e}")
            import traceback
            traceback.print_exc()
    
    # If we got data from H5 directly
    if ts_data is not None:
        logger.info(f"Time series data shape: {ts_data.shape if hasattr(ts_data, 'shape') else len(ts_data)}")
        
        # Calculate time index
        if initial_ts and resolution:
            # resolution might be in hours
            if isinstance(resolution, (int, float)):
                freq = f"{int(resolution)}h"
            else:
                freq = "1h"  # default to hourly
            
            time_index = pd.date_range(start=initial_ts, periods=len(ts_data), freq=freq)
        else:
            # Default: assume hourly starting from 2030-01-01
            time_index = pd.date_range(start="2030-01-01", periods=len(ts_data), freq="h")
        
        ts_series = pd.Series(ts_data, index=time_index)
        
        # Get value at target time
        if TARGET_TIME in ts_series.index:
            capacity_factor = ts_series.loc[TARGET_TIME]
        else:
            closest_idx = ts_series.index.get_indexer([TARGET_TIME], method='nearest')[0]
            closest_time = ts_series.index[closest_idx]
            capacity_factor = ts_series.loc[closest_time]
            logger.warning(f"Exact time not found, using closest: {closest_time}")
        
        available_power = capacity_factor * max_capacity
        
        print(f"\n{'='*60}")
        print(f"Results for {gen_data['name']} at {TARGET_TIME}")
        print(f"{'='*60}")
        print(f"Capacity factor (per-unit): {capacity_factor:.6f}")
        print(f"Max capacity: {max_capacity:.6f} MW")
        print(f"Available power: {available_power:.6f} MW")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    main()

