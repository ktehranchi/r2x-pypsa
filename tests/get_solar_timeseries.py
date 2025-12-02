#!/usr/bin/env python3
"""
Get solar capacity factors or output power for a specific generator at a specific time.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from r2x.api import System
from r2x.models import RenewableDispatch
from r2x.enums import PrimeMoversType
from loguru import logger

# File paths
H5_FILE = Path("/Users/henrydaniels-koch/Documents/Stanford_Grad_School/INES_Research/r2x-pypsa/tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.h5")
JSON_FILE = Path("/Users/henrydaniels-koch/Documents/Stanford_Grad_School/INES_Research/r2x-pypsa/tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json")

# Generator name and time
GEN_NAME = "p600 0 solar existing"
TARGET_TIME = pd.Timestamp("2030-01-01 00:00:00")

def load_system():
    """Load Sienna system from JSON and H5 files."""
    if not JSON_FILE.exists():
        raise FileNotFoundError(f"JSON file not found: {JSON_FILE}")
    if not H5_FILE.exists():
        raise FileNotFoundError(f"H5 file not found: {H5_FILE}")
    
    logger.info(f"Loading Sienna system from: {JSON_FILE}")
    logger.info(f"Time series data from: {H5_FILE}")
    
    # Load system from JSON (H5 file should be automatically linked)
    sys = System(str(JSON_FILE))
    
    # Try to set units (if method exists)
    try:
        sys.set_units_base_system("NATURAL_UNITS")
    except AttributeError:
        logger.warning("set_units_base_system() not available, assuming NATURAL_UNITS")
    
    return sys

def get_generator_timeseries(sys, gen_name, target_time):
    """Get capacity factors or output power for a specific generator at a specific time."""
    
    # Try different ways to access components
    # Method 1: get_components
    try:
        all_renewable = list(sys.get_components(RenewableDispatch))
        logger.info(f"Found {len(all_renewable)} RenewableDispatch generators via get_components()")
    except Exception as e:
        logger.warning(f"get_components() failed: {e}")
        all_renewable = []
    
    # Method 2: Try _component_mgr.iter_all() if available
    if len(all_renewable) == 0:
        try:
            from r2x.models import Generator
            all_components = list(sys._component_mgr.iter_all())
            all_renewable = [c for c in all_components if isinstance(c, RenewableDispatch)]
            logger.info(f"Found {len(all_renewable)} RenewableDispatch generators via _component_mgr")
        except Exception as e:
            logger.warning(f"_component_mgr.iter_all() failed: {e}")
    
    # Filter for the specific generator
    gen = None
    for g in all_renewable:
        if g.name == gen_name:
            gen = g
            break
    
    if gen is None:
        logger.error(f"Generator '{gen_name}' not found!")
        logger.info(f"Available RenewableDispatch generators (first 30):")
        for i, g in enumerate(all_renewable[:30]):
            logger.info(f"  {i+1}. {g.name} (prime_mover={g.prime_mover_type})")
        
        # Also check if there are any generators with similar names
        similar = [g.name for g in all_renewable if "p600" in g.name.lower() and "solar" in g.name.lower()]
        if similar:
            logger.info(f"\nGenerators with 'p600' and 'solar' in name:")
            for name in similar[:10]:
                logger.info(f"  - {name}")
        return None
    
    logger.info(f"Found generator: {gen.name}")
    logger.info(f"  Prime mover type: {gen.prime_mover_type}")
    logger.info(f"  Base power: {gen.base_power}")
    logger.info(f"  Rating: {gen.rating}")
    logger.info(f"  Power factor: {gen.power_factor}")
    
    # Calculate max capacity
    try:
        max_capacity = gen.get_max_active_power().magnitude if hasattr(gen.get_max_active_power(), 'magnitude') else gen.get_max_active_power()
    except:
        max_capacity = gen.rating * gen.power_factor * (gen.base_power.magnitude if hasattr(gen.base_power, 'magnitude') else gen.base_power)
    
    logger.info(f"  Max capacity (get_max_active_power): {max_capacity} MW")
    
    # Get time series
    time_series_list = list(sys.list_time_series(gen))
    logger.info(f"  Number of time series: {len(time_series_list)}")
    
    for ts in time_series_list:
        logger.info(f"    - {ts.name}: {type(ts.data)}")
    
    # Find max_active_power time series (capacity factors in per-unit)
    max_power_ts = None
    for ts in time_series_list:
        if ts.name == "max_active_power":
            max_power_ts = ts
            break
    
    if max_power_ts is None:
        logger.error("No 'max_active_power' time series found!")
        return None
    
    # Get time series data
    ts_data = max_power_ts.data
    
    # Convert to pandas Series if it's not already
    if hasattr(ts_data, 'index'):
        # Already a pandas Series
        ts_series = ts_data
    else:
        # Try to get index from time series
        try:
            # Check if time series has a time index
            if hasattr(max_power_ts, 'time_index'):
                index = max_power_ts.time_index
            elif hasattr(sys, 'get_time_series_index'):
                index = sys.get_time_series_index(gen, "max_active_power")
            else:
                # Try to infer from system
                logger.warning("Could not get time index, trying to infer...")
                # Create a default index based on data length
                # This is a fallback - ideally we'd get the actual time index
                index = pd.date_range(start="2030-01-01", periods=len(ts_data), freq="h")
            
            ts_series = pd.Series(ts_data, index=index)
        except Exception as e:
            logger.warning(f"Could not create pandas Series: {e}")
            logger.info(f"Time series data type: {type(ts_data)}")
            logger.info(f"Time series data shape: {getattr(ts_data, 'shape', 'unknown')}")
            # Try to access as array
            if hasattr(ts_data, '__iter__'):
                ts_array = np.array(list(ts_data))
                logger.info(f"Time series as array (first 10 values): {ts_array[:10]}")
                # Try to find the target time by position if we know the start time
                # For now, just return the first value as a test
                logger.info("Note: Cannot match exact time without proper time index")
                return {
                    'generator': gen_name,
                    'target_time': target_time,
                    'capacity_factor': ts_array[0] if len(ts_array) > 0 else None,
                    'available_power_mw': ts_array[0] * max_capacity if len(ts_array) > 0 else None,
                    'max_capacity_mw': max_capacity,
                }
            return None
    
    logger.info(f"Time series index type: {type(ts_series.index)}")
    logger.info(f"Time series length: {len(ts_series)}")
    logger.info(f"Time series index range: {ts_series.index[0]} to {ts_series.index[-1]}")
    
    # Find the value at target time
    if target_time in ts_series.index:
        capacity_factor = ts_series.loc[target_time]
    else:
        # Try to find closest time
        try:
            closest_idx = ts_series.index.get_indexer([target_time], method='nearest')[0]
            closest_time = ts_series.index[closest_idx]
            capacity_factor = ts_series.loc[closest_time]
            logger.warning(f"Exact time {target_time} not found, using closest: {closest_time}")
        except Exception as e:
            logger.error(f"Could not find time {target_time}: {e}")
            logger.info(f"Available times (first 10): {list(ts_series.index[:10])}")
            return None
    
    # Calculate available power (capacity_factor * max_capacity)
    available_power_mw = capacity_factor * max_capacity
    
    result = {
        'generator': gen_name,
        'time': target_time,
        'capacity_factor': capacity_factor,
        'max_capacity_mw': max_capacity,
        'available_power_mw': available_power_mw,
    }
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Results for {gen_name} at {target_time}")
    logger.info(f"{'='*60}")
    logger.info(f"Capacity factor (per-unit): {capacity_factor:.6f}")
    logger.info(f"Max capacity: {max_capacity:.6f} MW")
    logger.info(f"Available power: {available_power_mw:.6f} MW")
    logger.info(f"{'='*60}\n")
    
    return result

def main():
    """Main function."""
    try:
        sys = load_system()
        result = get_generator_timeseries(sys, GEN_NAME, TARGET_TIME)
        
        if result:
            print(f"\nGenerator: {result['generator']}")
            print(f"Time: {result['time']}")
            print(f"Capacity factor: {result['capacity_factor']:.6f}")
            print(f"Max capacity: {result['max_capacity_mw']:.6f} MW")
            print(f"Available power: {result['available_power_mw']:.6f} MW")
        else:
            print("Failed to get time series data")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()

