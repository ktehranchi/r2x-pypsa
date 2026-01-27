#!/usr/bin/env python3
"""Compare PyPSA and Sienna dispatch results visually with side-by-side plots."""

import pandas as pd
import matplotlib.pyplot as plt
import pypsa
import numpy as np
from pathlib import Path
import argparse
from loguru import logger
import sys

# Add tests directory to path to import helpers
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from helpers import plot_generator_marginal_costs


def load_pypsa_dispatch(csv_file):
    """Load PyPSA dispatch CSV and return DataFrame.
    
    Expected format: DateTime, carrier, value
    """
    csv_file = Path(csv_file)
    if not csv_file.exists():
        raise FileNotFoundError(f"PyPSA dispatch file not found: {csv_file}")
    
    df = pd.read_csv(csv_file)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    return df


def load_sienna_dispatch(csv_file):
    """Load Sienna dispatch CSV and return DataFrame.
    
    Expected format: DateTime, carrier, value
    """
    csv_file = Path(csv_file)
    if not csv_file.exists():
        raise FileNotFoundError(f"Sienna dispatch file not found: {csv_file}")
    
    df = pd.read_csv(csv_file)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    return df


def get_carrier_colors(network_file):
    """Load PyPSA network and extract carrier color mapping.
    
    Returns:
        dict: Mapping of carrier names to color hex codes
    """
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    
    # Default color palette for common carriers
    default_colors = {
        'coal': '#000000',
        'gas': '#FF6B6B',
        'nuclear': '#4ECDC4',
        'oil': '#FFE66D',
        'hydro': '#95E1D3',
        'onwind': '#A8E6CF',
        'offwind': '#88D8C0',
        'solar': '#FFD93D',
        'battery': '#6C5CE7',
        'other': '#9B59B6',  # Purple to distinguish from coal (black)
    }
    
    try:
        network = pypsa.Network(network_file)
        
        # Check if carriers have color column
        if 'color' not in network.carriers.columns:
            logger.warning("Network carriers do not have 'color' column. Using default colors.")
            # Use default colors or generate new ones
            carrier_colors = {}
            all_carriers = list(network.carriers.index)
            # Use a colormap to generate colors for carriers not in defaults
            cmap = cm.get_cmap('tab20')
            for i, carrier in enumerate(all_carriers):
                if carrier in default_colors:
                    carrier_colors[carrier] = default_colors[carrier]
                else:
                    # Generate a color from colormap
                    color = mcolors.rgb2hex(cmap(i % 20))
                    carrier_colors[carrier] = color
            return carrier_colors
        
        # Get colors and handle NaN values
        colors = network.carriers['color'].copy()
        
        # Fill NaN values with default or generated colors
        if colors.isna().any():
            missing_carriers = colors[colors.isna()].index.tolist()
            logger.warning(f"Carriers {missing_carriers} do not have colors. Using default/generated colors.")
            # Use default colors or generate new ones
            cmap = cm.get_cmap('tab20')
            for i, carrier in enumerate(missing_carriers):
                if carrier in default_colors:
                    colors.loc[carrier] = default_colors[carrier]
                else:
                    # Generate a color from colormap
                    color = mcolors.rgb2hex(cmap(i % 20))
                    colors.loc[carrier] = color
        
        # Convert to dict
        carrier_colors = colors.to_dict()
        
        # Ensure all values are valid hex colors
        for carrier, color in carrier_colors.items():
            if not color or pd.isna(color) or not isinstance(color, str):
                if carrier in default_colors:
                    carrier_colors[carrier] = default_colors[carrier]
                else:
                    carrier_colors[carrier] = '#808080'
        
        return carrier_colors
    
    except Exception as e:
        logger.warning(f"Error loading carrier colors from network: {e}. Using default colors.")
        return default_colors.copy()


def map_pypsa_to_fuel_carrier(pypsa_carrier):
    """Map PyPSA technology-specific carriers to fuel-based names for consistency.
    
    PyPSA uses technology-specific carriers like "CCGT" and "OCGT", while Sienna
    uses fuel types like "NATURAL_GAS". This function normalizes PyPSA carriers to
    fuel-based names to match Sienna output and the default color scheme.
    
    Parameters:
        pypsa_carrier: PyPSA carrier name (e.g., "CCGT", "OCGT", "coal", "solar")
        
    Returns:
        str: Fuel-based carrier name (e.g., "gas", "coal", "solar")
    """
    mapping = {
        # Thermal generators - map technology to fuel
        "CCGT": "gas",
        "OCGT": "gas",
        "CCGT-95CCS": "gas",
        "coal": "coal",
        "gas": "gas",
        "nuclear": "nuclear",
        "oil": "oil",
        "biomass": "biomass",
        "waste": "waste",
        "geothermal": "geothermal",
        "hydrogen_ct": "other",
        "other": "other",
        # Renewables - keep as-is (already match color scheme)
        "solar": "solar",
        "onwind": "onwind",
        "offwind": "offwind",
        "offwind_floating": "offwind",
        "wind": "onwind",  # Alias for onwind
        "hydro": "hydro",
        "ror": "hydro",  # Run-of-river hydro
        # Storage
        "battery": "battery",
        "pumped_hydro": "pumped_hydro",
    }
    
    # Try direct mapping first
    if pypsa_carrier in mapping:
        return mapping[pypsa_carrier]
    
    # Try case-insensitive match
    pypsa_lower = pypsa_carrier.lower()
    for key, value in mapping.items():
        if key.lower() == pypsa_lower:
            return value
    
    # If no mapping found, return original (will use default color if available)
    return pypsa_carrier


def map_sienna_to_pypsa_carrier(sienna_carrier):
    """Map Sienna carrier names (prime mover types/fuel types) to PyPSA carrier names.
    
    Sienna uses:
    - Prime mover types for renewables: "WT" (wind), "PVe" (solar), "HY" (hydro)
    - Fuel types for thermal: "COAL", "NATURAL_GAS", etc.
    
    PyPSA uses:
    - Carrier names: "onwind", "solar", "hydro", "coal", "gas", etc.
    
    Returns:
        str: PyPSA carrier name
    """
    mapping = {
        # Prime mover types -> PyPSA carriers
        "WT": "onwind",
        "WS": "offwind", 
        "PVe": "solar",
        "HY": "hydro",
        # Fuel types -> PyPSA carriers
        "COAL": "coal",
        "NATURAL_GAS": "gas",
        "NUCLEAR": "nuclear",
        "DISTILLATE_FUEL_OIL": "oil",
        "OTHER": "other",
        # Storage
        "battery": "battery",
    }
    # Try direct mapping first
    if sienna_carrier in mapping:
        return mapping[sienna_carrier]
    
    # Try case-insensitive match
    sienna_lower = sienna_carrier.upper()
    for key, value in mapping.items():
        if key.upper() == sienna_lower:
            return value
    
    # If no mapping found, return original (will use default color)
    return sienna_carrier


def compare_hourly_wind_dispatch(pypsa_df, sienna_df, timesteps=168):
    """Compare hourly wind dispatch between PyPSA and Sienna to identify timestamp issues.
    
    Parameters:
        pypsa_df: DataFrame with columns DateTime, carrier, value
        sienna_df: DataFrame with columns DateTime, carrier, value
        timesteps: Number of timesteps to compare (default: 168 for 1 week)
    """
    logger.info("=" * 80)
    logger.info("HOURLY WIND DISPATCH COMPARISON")
    logger.info("=" * 80)
    
    try:
        # Filter wind data from PyPSA (onwind and offwind)
        pypsa_wind = pypsa_df[pypsa_df['carrier'].isin(['onwind', 'offwind'])].copy()
        # Filter wind data from Sienna (WT = wind turbine)
        sienna_wind = sienna_df[sienna_df['carrier'] == 'WT'].copy()
        
        if len(pypsa_wind) == 0:
            logger.warning("No PyPSA wind data found")
            return
        if len(sienna_wind) == 0:
            logger.warning("No Sienna wind data found")
            return
        
        # Aggregate by DateTime for each system
        pypsa_wind_hourly = pypsa_wind.groupby('DateTime')['value'].sum().reset_index()
        sienna_wind_hourly = sienna_wind.groupby('DateTime')['value'].sum().reset_index()
        
        # Sort by DateTime
        pypsa_wind_hourly = pypsa_wind_hourly.sort_values('DateTime').reset_index(drop=True)
        sienna_wind_hourly = sienna_wind_hourly.sort_values('DateTime').reset_index(drop=True)
        
        # Limit to specified timesteps
        pypsa_wind_hourly = pypsa_wind_hourly.iloc[:timesteps]
        sienna_wind_hourly = sienna_wind_hourly.iloc[:timesteps]
        
        logger.info(f"PyPSA wind records: {len(pypsa_wind_hourly)} timesteps")
        logger.info(f"Sienna wind records: {len(sienna_wind_hourly)} timesteps")
        
        # Check timestamp alignment
        pypsa_dates = set(pypsa_wind_hourly['DateTime'].dt.normalize())
        sienna_dates = set(sienna_wind_hourly['DateTime'].dt.normalize())
        common_dates = pypsa_dates & sienna_dates
        
        logger.info(f"PyPSA unique dates: {len(pypsa_dates)}")
        logger.info(f"Sienna unique dates: {len(sienna_dates)}")
        logger.info(f"Common dates: {len(common_dates)}")
        
        if len(common_dates) == 0:
            logger.warning("⚠️  NO COMMON DATES FOUND - TIMESTAMP MISMATCH!")
            logger.info(f"PyPSA date range: {pypsa_wind_hourly['DateTime'].min()} to {pypsa_wind_hourly['DateTime'].max()}")
            logger.info(f"Sienna date range: {sienna_wind_hourly['DateTime'].min()} to {sienna_wind_hourly['DateTime'].max()}")
            return
        
        # Try to align by index position (assuming same time period, just different timestamp formats)
        logger.info("\n" + "-" * 80)
        logger.info("COMPARING BY INDEX POSITION (assuming same time period)")
        logger.info("-" * 80)
        
        min_len = min(len(pypsa_wind_hourly), len(sienna_wind_hourly))
        mismatches = []
        matches = []
        
        for i in range(min_len):
            pypsa_val = pypsa_wind_hourly.iloc[i]['value']
            sienna_val = sienna_wind_hourly.iloc[i]['value']
            pypsa_ts = pypsa_wind_hourly.iloc[i]['DateTime']
            sienna_ts = sienna_wind_hourly.iloc[i]['DateTime']
            
            diff = abs(pypsa_val - sienna_val)
            diff_pct = (diff / max(abs(pypsa_val), 1.0)) * 100 if max(abs(pypsa_val), abs(sienna_val)) > 0.01 else 0.0
            
            # Check if timestamps match (within 1 hour)
            ts_diff = abs((pypsa_ts - sienna_ts).total_seconds() / 3600)
            
            if diff > 0.01:  # More than 0.01 MW difference
                mismatches.append({
                    'index': i,
                    'pypsa_ts': pypsa_ts,
                    'sienna_ts': sienna_ts,
                    'ts_diff_hours': ts_diff,
                    'pypsa_val': pypsa_val,
                    'sienna_val': sienna_val,
                    'diff_mw': diff,
                    'diff_pct': diff_pct
                })
            else:
                matches.append(i)
        
        logger.info(f"Matches (diff <= 0.01 MW): {len(matches)}/{min_len} ({len(matches)/min_len*100:.1f}%)")
        logger.info(f"Mismatches (diff > 0.01 MW): {len(mismatches)}/{min_len} ({len(mismatches)/min_len*100:.1f}%)")
        
        if len(mismatches) > 0:
            logger.info("\n" + "-" * 80)
            logger.info("TOP 20 MISMATCHES (by absolute difference):")
            logger.info("-" * 80)
            logger.info(f"{'Index':<8} {'PyPSA TS':<20} {'Sienna TS':<20} {'TS Diff':<10} {'PyPSA (MW)':<12} {'Sienna (MW)':<12} {'Diff (MW)':<12} {'Diff (%)':<10}")
            logger.info("-" * 80)
            
            # Sort by absolute difference
            mismatches_sorted = sorted(mismatches, key=lambda x: x['diff_mw'], reverse=True)
            
            for m in mismatches_sorted[:20]:
                logger.info(
                    f"{m['index']:<8} "
                    f"{str(m['pypsa_ts']):<20} "
                    f"{str(m['sienna_ts']):<20} "
                    f"{m['ts_diff_hours']:<10.2f} "
                    f"{m['pypsa_val']:<12.2f} "
                    f"{m['sienna_val']:<12.2f} "
                    f"{m['diff_mw']:<12.2f} "
                    f"{m['diff_pct']:<10.2f}"
                )
            
            # Check for timestamp misalignment patterns
            logger.info("\n" + "-" * 80)
            logger.info("TIMESTAMP ALIGNMENT ANALYSIS:")
            logger.info("-" * 80)
            
            ts_diffs = [m['ts_diff_hours'] for m in mismatches]
            if len(ts_diffs) > 0:
                logger.info(f"Timestamp differences in mismatches:")
                logger.info(f"  Min: {min(ts_diffs):.2f} hours")
                logger.info(f"  Max: {max(ts_diffs):.2f} hours")
                logger.info(f"  Mean: {np.mean(ts_diffs):.2f} hours")
                logger.info(f"  Median: {np.median(ts_diffs):.2f} hours")
                
                # Count how many have significant timestamp differences (> 0.5 hours)
                significant_ts_diff = sum(1 for d in ts_diffs if d > 0.5)
                logger.info(f"  Mismatches with TS diff > 0.5 hours: {significant_ts_diff}/{len(ts_diffs)} ({significant_ts_diff/len(ts_diffs)*100:.1f}%)")
        
        # Summary statistics
        logger.info("\n" + "-" * 80)
        logger.info("SUMMARY STATISTICS:")
        logger.info("-" * 80)
        logger.info(f"PyPSA wind total: {pypsa_wind_hourly['value'].sum():.2f} MWh")
        logger.info(f"Sienna wind total: {sienna_wind_hourly['value'].sum():.2f} MWh")
        logger.info(f"Total difference: {abs(pypsa_wind_hourly['value'].sum() - sienna_wind_hourly['value'].sum()):.2f} MWh")
        logger.info(f"PyPSA wind mean: {pypsa_wind_hourly['value'].mean():.2f} MW")
        logger.info(f"Sienna wind mean: {sienna_wind_hourly['value'].mean():.2f} MW")
        logger.info(f"PyPSA wind max: {pypsa_wind_hourly['value'].max():.2f} MW")
        logger.info(f"Sienna wind max: {sienna_wind_hourly['value'].max():.2f} MW")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error comparing hourly wind dispatch: {e}")
        import traceback
        logger.error(traceback.format_exc())


def compare_hourly_renewables_dispatch(pypsa_df, sienna_df, timesteps=168):
    """Compare hourly renewables dispatch (solar, wind, hydro combined) between PyPSA and Sienna.
    
    Since all renewables have marginal costs of 0, we combine them for comparison.
    
    Parameters:
        pypsa_df: DataFrame with columns DateTime, carrier, value
        sienna_df: DataFrame with columns DateTime, carrier, value
        timesteps: Number of timesteps to compare (default: 168 for 1 week)
    """
    logger.info("=" * 80)
    logger.info("HOURLY RENEWABLES DISPATCH COMPARISON (Solar + Wind + Hydro)")
    logger.info("=" * 80)
    
    try:
        # Filter renewables from PyPSA (solar, onwind, offwind, hydro)
        pypsa_renewables = pypsa_df[pypsa_df['carrier'].isin(['solar', 'onwind', 'offwind', 'hydro'])].copy()
        # Filter renewables from Sienna (PVe = solar, WT = wind, WS = offshore wind, HY = hydro)
        # Map Sienna carriers to PyPSA names first
        sienna_df_mapped = sienna_df.copy()
        sienna_df_mapped['carrier'] = sienna_df_mapped['carrier'].apply(map_sienna_to_pypsa_carrier)
        sienna_renewables = sienna_df_mapped[sienna_df_mapped['carrier'].isin(['solar', 'onwind', 'offwind', 'hydro'])].copy()
        
        if len(pypsa_renewables) == 0:
            logger.warning("No PyPSA renewables data found")
            return
        if len(sienna_renewables) == 0:
            logger.warning("No Sienna renewables data found")
            return
        
        # Aggregate by DateTime for each system
        pypsa_renewables_hourly = pypsa_renewables.groupby('DateTime')['value'].sum().reset_index()
        sienna_renewables_hourly = sienna_renewables.groupby('DateTime')['value'].sum().reset_index()
        
        # Sort by DateTime
        pypsa_renewables_hourly = pypsa_renewables_hourly.sort_values('DateTime').reset_index(drop=True)
        sienna_renewables_hourly = sienna_renewables_hourly.sort_values('DateTime').reset_index(drop=True)
        
        # Limit to specified timesteps
        pypsa_renewables_hourly = pypsa_renewables_hourly.iloc[:timesteps]
        sienna_renewables_hourly = sienna_renewables_hourly.iloc[:timesteps]
        
        logger.info(f"PyPSA renewables records: {len(pypsa_renewables_hourly)} timesteps")
        logger.info(f"Sienna renewables records: {len(sienna_renewables_hourly)} timesteps")
        
        # Check timestamp alignment
        pypsa_dates = set(pypsa_renewables_hourly['DateTime'].dt.normalize())
        sienna_dates = set(sienna_renewables_hourly['DateTime'].dt.normalize())
        common_dates = pypsa_dates & sienna_dates
        
        logger.info(f"PyPSA unique dates: {len(pypsa_dates)}")
        logger.info(f"Sienna unique dates: {len(sienna_dates)}")
        logger.info(f"Common dates: {len(common_dates)}")
        
        if len(common_dates) == 0:
            logger.warning("⚠️  NO COMMON DATES FOUND - TIMESTAMP MISMATCH!")
            logger.info(f"PyPSA date range: {pypsa_renewables_hourly['DateTime'].min()} to {pypsa_renewables_hourly['DateTime'].max()}")
            logger.info(f"Sienna date range: {sienna_renewables_hourly['DateTime'].min()} to {sienna_renewables_hourly['DateTime'].max()}")
            return
        
        # Try to align by index position (assuming same time period, just different timestamp formats)
        logger.info("\n" + "-" * 80)
        logger.info("COMPARING BY INDEX POSITION (assuming same time period)")
        logger.info("-" * 80)
        
        min_len = min(len(pypsa_renewables_hourly), len(sienna_renewables_hourly))
        mismatches = []
        matches = []
        
        for i in range(min_len):
            pypsa_val = pypsa_renewables_hourly.iloc[i]['value']
            sienna_val = sienna_renewables_hourly.iloc[i]['value']
            pypsa_ts = pypsa_renewables_hourly.iloc[i]['DateTime']
            sienna_ts = sienna_renewables_hourly.iloc[i]['DateTime']
            
            diff = abs(pypsa_val - sienna_val)
            diff_pct = (diff / max(abs(pypsa_val), 1.0)) * 100 if max(abs(pypsa_val), abs(sienna_val)) > 0.01 else 0.0
            
            # Check if timestamps match (within 1 hour)
            ts_diff = abs((pypsa_ts - sienna_ts).total_seconds() / 3600)
            
            if diff > 0.01:  # More than 0.01 MW difference
                mismatches.append({
                    'index': i,
                    'pypsa_ts': pypsa_ts,
                    'sienna_ts': sienna_ts,
                    'ts_diff_hours': ts_diff,
                    'pypsa_val': pypsa_val,
                    'sienna_val': sienna_val,
                    'diff_mw': diff,
                    'diff_pct': diff_pct
                })
            else:
                matches.append(i)
        
        logger.info(f"Matches (diff <= 0.01 MW): {len(matches)}/{min_len} ({len(matches)/min_len*100:.1f}%)")
        logger.info(f"Mismatches (diff > 0.01 MW): {len(mismatches)}/{min_len} ({len(mismatches)/min_len*100:.1f}%)")
        
        if len(mismatches) > 0:
            logger.info("\n" + "-" * 80)
            logger.info("TOP 20 MISMATCHES (by absolute difference):")
            logger.info("-" * 80)
            logger.info(f"{'Index':<8} {'PyPSA TS':<20} {'Sienna TS':<20} {'TS Diff':<10} {'PyPSA (MW)':<12} {'Sienna (MW)':<12} {'Diff (MW)':<12} {'Diff (%)':<10}")
            logger.info("-" * 80)
            
            # Sort by absolute difference
            mismatches_sorted = sorted(mismatches, key=lambda x: x['diff_mw'], reverse=True)
            
            for m in mismatches_sorted[:20]:
                logger.info(
                    f"{m['index']:<8} "
                    f"{str(m['pypsa_ts']):<20} "
                    f"{str(m['sienna_ts']):<20} "
                    f"{m['ts_diff_hours']:<10.2f} "
                    f"{m['pypsa_val']:<12.2f} "
                    f"{m['sienna_val']:<12.2f} "
                    f"{m['diff_mw']:<12.2f} "
                    f"{m['diff_pct']:<10.2f}"
                )
            
            # Check for timestamp misalignment patterns
            logger.info("\n" + "-" * 80)
            logger.info("TIMESTAMP ALIGNMENT ANALYSIS:")
            logger.info("-" * 80)
            
            ts_diffs = [m['ts_diff_hours'] for m in mismatches]
            if len(ts_diffs) > 0:
                logger.info(f"Timestamp differences in mismatches:")
                logger.info(f"  Min: {min(ts_diffs):.2f} hours")
                logger.info(f"  Max: {max(ts_diffs):.2f} hours")
                logger.info(f"  Mean: {np.mean(ts_diffs):.2f} hours")
                logger.info(f"  Median: {np.median(ts_diffs):.2f} hours")
                
                # Count how many have significant timestamp differences (> 0.5 hours)
                significant_ts_diff = sum(1 for d in ts_diffs if d > 0.5)
                logger.info(f"  Mismatches with TS diff > 0.5 hours: {significant_ts_diff}/{len(ts_diffs)} ({significant_ts_diff/len(ts_diffs)*100:.1f}%)")
        
        # Summary statistics
        logger.info("\n" + "-" * 80)
        logger.info("SUMMARY STATISTICS:")
        logger.info("-" * 80)
        logger.info(f"PyPSA renewables total: {pypsa_renewables_hourly['value'].sum():.2f} MWh")
        logger.info(f"Sienna renewables total: {sienna_renewables_hourly['value'].sum():.2f} MWh")
        logger.info(f"Total difference: {abs(pypsa_renewables_hourly['value'].sum() - sienna_renewables_hourly['value'].sum()):.2f} MWh")
        logger.info(f"PyPSA renewables mean: {pypsa_renewables_hourly['value'].mean():.2f} MW")
        logger.info(f"Sienna renewables mean: {sienna_renewables_hourly['value'].mean():.2f} MW")
        logger.info(f"PyPSA renewables max: {pypsa_renewables_hourly['value'].max():.2f} MW")
        logger.info(f"Sienna renewables max: {sienna_renewables_hourly['value'].max():.2f} MW")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error comparing hourly renewables dispatch: {e}")
        import traceback
        logger.error(traceback.format_exc())


def compare_hourly_nuclear_dispatch(pypsa_df, sienna_df, timesteps=168):
    """Compare hourly nuclear dispatch between PyPSA and Sienna.
    
    Parameters:
        pypsa_df: DataFrame with columns DateTime, carrier, value
        sienna_df: DataFrame with columns DateTime, carrier, value
        timesteps: Number of timesteps to compare (default: 168 for 1 week)
    """
    logger.info("=" * 80)
    logger.info("HOURLY NUCLEAR DISPATCH COMPARISON")
    logger.info("=" * 80)
    
    try:
        # Filter nuclear data from PyPSA
        pypsa_nuclear = pypsa_df[pypsa_df['carrier'] == 'nuclear'].copy()
        # Filter nuclear data from Sienna (map Sienna carrier to PyPSA name)
        sienna_df_mapped = sienna_df.copy()
        sienna_df_mapped['carrier'] = sienna_df_mapped['carrier'].apply(map_sienna_to_pypsa_carrier)
        sienna_nuclear = sienna_df_mapped[sienna_df_mapped['carrier'] == 'nuclear'].copy()
        
        if len(pypsa_nuclear) == 0:
            logger.warning("No PyPSA nuclear data found")
            return
        if len(sienna_nuclear) == 0:
            logger.warning("No Sienna nuclear data found")
            return
        
        # Aggregate by DateTime for each system
        pypsa_nuclear_hourly = pypsa_nuclear.groupby('DateTime')['value'].sum().reset_index()
        sienna_nuclear_hourly = sienna_nuclear.groupby('DateTime')['value'].sum().reset_index()
        
        # Sort by DateTime
        pypsa_nuclear_hourly = pypsa_nuclear_hourly.sort_values('DateTime').reset_index(drop=True)
        sienna_nuclear_hourly = sienna_nuclear_hourly.sort_values('DateTime').reset_index(drop=True)
        
        # Limit to specified timesteps
        pypsa_nuclear_hourly = pypsa_nuclear_hourly.iloc[:timesteps]
        sienna_nuclear_hourly = sienna_nuclear_hourly.iloc[:timesteps]
        
        logger.info(f"PyPSA nuclear records: {len(pypsa_nuclear_hourly)} timesteps")
        logger.info(f"Sienna nuclear records: {len(sienna_nuclear_hourly)} timesteps")
        
        # Check timestamp alignment
        pypsa_dates = set(pypsa_nuclear_hourly['DateTime'].dt.normalize())
        sienna_dates = set(sienna_nuclear_hourly['DateTime'].dt.normalize())
        common_dates = pypsa_dates & sienna_dates
        
        logger.info(f"PyPSA unique dates: {len(pypsa_dates)}")
        logger.info(f"Sienna unique dates: {len(sienna_dates)}")
        logger.info(f"Common dates: {len(common_dates)}")
        
        if len(common_dates) == 0:
            logger.warning("⚠️  NO COMMON DATES FOUND - TIMESTAMP MISMATCH!")
            logger.info(f"PyPSA date range: {pypsa_nuclear_hourly['DateTime'].min()} to {pypsa_nuclear_hourly['DateTime'].max()}")
            logger.info(f"Sienna date range: {sienna_nuclear_hourly['DateTime'].min()} to {sienna_nuclear_hourly['DateTime'].max()}")
            return
        
        # Try to align by index position (assuming same time period, just different timestamp formats)
        logger.info("\n" + "-" * 80)
        logger.info("COMPARING BY INDEX POSITION (assuming same time period)")
        logger.info("-" * 80)
        
        min_len = min(len(pypsa_nuclear_hourly), len(sienna_nuclear_hourly))
        mismatches = []
        matches = []
        
        for i in range(min_len):
            pypsa_val = pypsa_nuclear_hourly.iloc[i]['value']
            sienna_val = sienna_nuclear_hourly.iloc[i]['value']
            pypsa_ts = pypsa_nuclear_hourly.iloc[i]['DateTime']
            sienna_ts = sienna_nuclear_hourly.iloc[i]['DateTime']
            
            diff = abs(pypsa_val - sienna_val)
            diff_pct = (diff / max(abs(pypsa_val), 1.0)) * 100 if max(abs(pypsa_val), abs(sienna_val)) > 0.01 else 0.0
            
            # Check if timestamps match (within 1 hour)
            ts_diff = abs((pypsa_ts - sienna_ts).total_seconds() / 3600)
            
            if diff > 0.01:  # More than 0.01 MW difference
                mismatches.append({
                    'index': i,
                    'pypsa_ts': pypsa_ts,
                    'sienna_ts': sienna_ts,
                    'ts_diff_hours': ts_diff,
                    'pypsa_val': pypsa_val,
                    'sienna_val': sienna_val,
                    'diff_mw': diff,
                    'diff_pct': diff_pct
                })
            else:
                matches.append(i)
        
        logger.info(f"Matches (diff <= 0.01 MW): {len(matches)}/{min_len} ({len(matches)/min_len*100:.1f}%)")
        logger.info(f"Mismatches (diff > 0.01 MW): {len(mismatches)}/{min_len} ({len(mismatches)/min_len*100:.1f}%)")
        
        if len(mismatches) > 0:
            logger.info("\n" + "-" * 80)
            logger.info("TOP 20 MISMATCHES (by absolute difference):")
            logger.info("-" * 80)
            logger.info(f"{'Index':<8} {'PyPSA TS':<20} {'Sienna TS':<20} {'TS Diff':<10} {'PyPSA (MW)':<12} {'Sienna (MW)':<12} {'Diff (MW)':<12} {'Diff (%)':<10}")
            logger.info("-" * 80)
            
            # Sort by absolute difference
            mismatches_sorted = sorted(mismatches, key=lambda x: x['diff_mw'], reverse=True)
            
            for m in mismatches_sorted[:20]:
                logger.info(
                    f"{m['index']:<8} "
                    f"{str(m['pypsa_ts']):<20} "
                    f"{str(m['sienna_ts']):<20} "
                    f"{m['ts_diff_hours']:<10.2f} "
                    f"{m['pypsa_val']:<12.2f} "
                    f"{m['sienna_val']:<12.2f} "
                    f"{m['diff_mw']:<12.2f} "
                    f"{m['diff_pct']:<10.2f}"
                )
            
            # Check for timestamp misalignment patterns
            logger.info("\n" + "-" * 80)
            logger.info("TIMESTAMP ALIGNMENT ANALYSIS:")
            logger.info("-" * 80)
            
            ts_diffs = [m['ts_diff_hours'] for m in mismatches]
            if len(ts_diffs) > 0:
                logger.info(f"Timestamp differences in mismatches:")
                logger.info(f"  Min: {min(ts_diffs):.2f} hours")
                logger.info(f"  Max: {max(ts_diffs):.2f} hours")
                logger.info(f"  Mean: {np.mean(ts_diffs):.2f} hours")
                logger.info(f"  Median: {np.median(ts_diffs):.2f} hours")
                
                # Count how many have significant timestamp differences (> 0.5 hours)
                significant_ts_diff = sum(1 for d in ts_diffs if d > 0.5)
                logger.info(f"  Mismatches with TS diff > 0.5 hours: {significant_ts_diff}/{len(ts_diffs)} ({significant_ts_diff/len(ts_diffs)*100:.1f}%)")
        
        # Summary statistics
        logger.info("\n" + "-" * 80)
        logger.info("SUMMARY STATISTICS:")
        logger.info("-" * 80)
        logger.info(f"PyPSA nuclear total: {pypsa_nuclear_hourly['value'].sum():.2f} MWh")
        logger.info(f"Sienna nuclear total: {sienna_nuclear_hourly['value'].sum():.2f} MWh")
        logger.info(f"Total difference: {abs(pypsa_nuclear_hourly['value'].sum() - sienna_nuclear_hourly['value'].sum()):.2f} MWh")
        logger.info(f"PyPSA nuclear mean: {pypsa_nuclear_hourly['value'].mean():.2f} MW")
        logger.info(f"Sienna nuclear mean: {sienna_nuclear_hourly['value'].mean():.2f} MW")
        logger.info(f"PyPSA nuclear max: {pypsa_nuclear_hourly['value'].max():.2f} MW")
        logger.info(f"Sienna nuclear max: {sienna_nuclear_hourly['value'].max():.2f} MW")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error comparing hourly nuclear dispatch: {e}")
        import traceback
        logger.error(traceback.format_exc())


def order_carriers_by_marginal_cost(carriers):
    """Order carriers by typical marginal cost (lowest first).
    
    Typical order (bottom to top in dispatch plot):
    1. Renewables - ~0 $/MWh (solar first, then wind, then hydro)
    2. Nuclear - ~0-5 $/MWh
    3. Batteries - variable, but typically after renewables
    4. Thermal (gas, coal, oil) - higher costs
    
    Parameters:
        carriers: List or set of carrier names
        
    Returns:
        List of carriers ordered by typical marginal cost (ascending)
    """
    # Define typical marginal cost order (lower number = lower cost, appears at bottom)
    cost_order = {
        # Renewables - lowest cost, bottom of stack
        # Solar first, then wind, then hydro
        'solar': 0.5,
        'onwind': 1,
        'offwind': 1,
        'wind': 1,  # Alias for onwind
        'hydro': 0.01,
        # Nuclear - very low cost, after renewables
        'nuclear': 0.0,
        # Batteries - after renewables but before thermal
        'battery': 3,
        'pumped_hydro': 3,
        # Thermal - higher costs, top of stack
        'gas': 4,
        'coal': 5,
        'oil': 6,
        'biomass': 7,
        'waste': 8,
        'geothermal': 9,
        'other': 10,
    }
    
    # Sort carriers by cost order, then alphabetically for ties
    def get_order(carrier):
        return (cost_order.get(carrier.lower(), 999), carrier.lower())
    
    return sorted(carriers, key=get_order)


def plot_side_by_side_energy_balance(pypsa_df, sienna_df, carrier_colors, timesteps=168, output_file=None):
    """Create side-by-side energy balance plots.
    
    Parameters:
        pypsa_df: DataFrame with columns DateTime, carrier, value
        sienna_df: DataFrame with columns DateTime, carrier, value
        carrier_colors: dict mapping carrier names to colors
        timesteps: Number of timesteps to plot (default: 168 for 1 week)
        output_file: Optional path to save the plot
    """
    # Map PyPSA carriers to fuel-based names for consistency
    pypsa_df_mapped = pypsa_df.copy()
    pypsa_df_mapped['carrier'] = pypsa_df_mapped['carrier'].apply(map_pypsa_to_fuel_carrier)
    
    # Map Sienna carrier names to fuel-based names for consistency
    sienna_df_mapped = sienna_df.copy()
    sienna_df_mapped['carrier'] = sienna_df_mapped['carrier'].apply(map_sienna_to_pypsa_carrier)
    
    # Detailed hourly nuclear dispatch comparison
    compare_hourly_nuclear_dispatch(pypsa_df, sienna_df, timesteps=timesteps)
    
    # Note: Removed compare_hourly_renewables_dispatch - renewables are now shown separately by carrier
    
    # Identify load carriers (common names: 'load', 'AC', 'loads')
    load_carriers = {'load', 'AC', 'loads', 'demand'}

    # Carriers to exclude from dispatch plots (not actual generation)
    exclude_carriers = {'interchange','link'}  # Transfer between regions, not generation
    
    # Debug: log unique carriers to see what we have
    logger.debug(f"PyPSA unique carriers (after mapping): {sorted(pypsa_df_mapped['carrier'].unique())}")
    logger.debug(f"Sienna unique carriers (after mapping): {sorted(sienna_df_mapped['carrier'].unique())}")
    
    # Separate load from generators for PyPSA (also exclude link flows)
    pypsa_load_mask = pypsa_df_mapped['carrier'].str.upper().isin([c.upper() for c in load_carriers])
    pypsa_exclude_mask = pypsa_df_mapped['carrier'].str.lower().isin([c.lower() for c in exclude_carriers])
    pypsa_generators_df = pypsa_df_mapped[~pypsa_load_mask & ~pypsa_exclude_mask].copy()
    pypsa_load_df = pypsa_df_mapped[pypsa_load_mask].copy()

    # Separate load from generators for Sienna (also exclude interchange)
    sienna_load_mask = sienna_df_mapped['carrier'].str.upper().isin([c.upper() for c in load_carriers])
    sienna_exclude_mask = sienna_df_mapped['carrier'].str.lower().isin([c.lower() for c in exclude_carriers])
    sienna_generators_df = sienna_df_mapped[~sienna_load_mask & ~sienna_exclude_mask].copy()
    sienna_load_df = sienna_df_mapped[sienna_load_mask].copy()
    
    logger.debug(f"PyPSA load records: {len(pypsa_load_df)}, Sienna load records: {len(sienna_load_df)}")
    
    # Pivot to get carriers as columns, time as index (generators only)
    pypsa_balance = pypsa_generators_df.pivot_table(
        index='DateTime',
        columns='carrier',
        values='value',
        aggfunc='sum'
    ).fillna(0)
    
    sienna_balance = sienna_generators_df.pivot_table(
        index='DateTime',
        columns='carrier',
        values='value',
        aggfunc='sum'
    ).fillna(0)
    
    # Aggregate load data (sum all load carriers per timestep)
    # Scale load correctly: PyPSA 'load' carrier needs *100, 'AC' is already in MW
    # Sienna 'load' carrier needs *100
    if len(pypsa_load_df) > 0:
        # Scale 'load' carrier by 100, keep 'AC' as-is (already in MW)
        pypsa_load_scaled = pypsa_load_df.copy()
        pypsa_load_scaled['value_scaled'] = pypsa_load_scaled.apply(
            lambda row: row['value'] * 100 if row['carrier'] == 'load' else row['value'],
            axis=1
        )
        pypsa_load_total = pypsa_load_scaled.groupby('DateTime')['value_scaled'].sum().abs()
        logger.debug(f"PyPSA load total: min={pypsa_load_total.min():.2f}, max={pypsa_load_total.max():.2f}, mean={pypsa_load_total.mean():.2f}")
    else:
        pypsa_load_total = pd.Series(dtype=float)
    
    if len(sienna_load_df) > 0:
        # Scale Sienna 'load' carrier by 100
        sienna_load_scaled = sienna_load_df.copy()
        sienna_load_scaled['value_scaled'] = sienna_load_scaled['value'] * 100
        sienna_load_total = sienna_load_scaled.groupby('DateTime')['value_scaled'].sum().abs()
        logger.debug(f"Sienna load total: min={sienna_load_total.min():.2f}, max={sienna_load_total.max():.2f}, mean={sienna_load_total.mean():.2f}")
    else:
        sienna_load_total = pd.Series(dtype=float)
    
    # Limit to specified timesteps
    if timesteps is not None:
        pypsa_balance = pypsa_balance.iloc[:timesteps]
        sienna_balance = sienna_balance.iloc[:timesteps]
        if len(pypsa_load_total) > 0:
            pypsa_load_total = pypsa_load_total.iloc[:timesteps]
        if len(sienna_load_total) > 0:
            sienna_load_total = sienna_load_total.iloc[:timesteps]
    
    # Align load series with balance index (use intersection to preserve actual values)
    if len(pypsa_load_total) > 0:
        # Reindex to match balance index, but only fill missing values (not all zeros)
        pypsa_load_total = pypsa_load_total.reindex(pypsa_balance.index)
        # Fill NaN with 0 only for missing timesteps
        pypsa_load_total = pypsa_load_total.fillna(0)
        logger.debug(f"After alignment: PyPSA load has {len(pypsa_load_total)} points, {pypsa_load_total.abs().sum():.2f} total")
    else:
        pypsa_load_total = pd.Series(0, index=pypsa_balance.index)
        logger.debug("PyPSA load is empty, creating zero series")
    
    if len(sienna_load_total) > 0:
        # Reindex to match balance index, but only fill missing values (not all zeros)
        sienna_load_total = sienna_load_total.reindex(sienna_balance.index)
        # Fill NaN with 0 only for missing timesteps
        sienna_load_total = sienna_load_total.fillna(0)
        logger.debug(f"After alignment: Sienna load has {len(sienna_load_total)} points, {sienna_load_total.abs().sum():.2f} total")
    else:
        sienna_load_total = pd.Series(0, index=sienna_balance.index)
        logger.debug("Sienna load is empty, creating zero series")
    
    # Separate positive and negative values (generators only)
    pypsa_pos = pypsa_balance.clip(lower=0)
    pypsa_neg = pypsa_balance.clip(upper=0)
    sienna_pos = sienna_balance.clip(lower=0)
    sienna_neg = sienna_balance.clip(upper=0)
    
    # Get all unique generator carriers from both datasets
    # Order by typical marginal cost (lowest first, appears at bottom of stack)
    all_carriers = order_carriers_by_marginal_cost(set(pypsa_balance.columns) | set(sienna_balance.columns))
    
    # Ensure both DataFrames have the same columns (fill missing with 0)
    for carrier in all_carriers:
        if carrier not in pypsa_balance.columns:
            pypsa_balance[carrier] = 0
            pypsa_pos[carrier] = 0
            pypsa_neg[carrier] = 0
        if carrier not in sienna_balance.columns:
            sienna_balance[carrier] = 0
            sienna_pos[carrier] = 0
            sienna_neg[carrier] = 0
    
    # Reorder columns to match
    pypsa_balance = pypsa_balance[all_carriers]
    pypsa_pos = pypsa_pos[all_carriers]
    pypsa_neg = pypsa_neg[all_carriers]
    sienna_balance = sienna_balance[all_carriers]
    sienna_pos = sienna_pos[all_carriers]
    sienna_neg = sienna_neg[all_carriers]
    
    # Map carrier colors from original PyPSA carrier names to fuel-based names
    # This handles cases where CCGT/OCGT both map to "gas"
    fuel_based_colors = {}
    default_colors = {
        'coal': '#000000',
        'gas': '#FF6B6B',
        'nuclear': '#4ECDC4',
        'oil': '#FFE66D',
        'hydro': '#95E1D3',
        'onwind': '#A8E6CF',
        'offwind': '#88D8C0',
        'solar': '#FFD93D',
        'battery': '#6C5CE7',
        'other': '#9B59B6',  # Purple to distinguish from coal (black)
    }
    
    # Get original carrier names from pypsa_df (before mapping)
    original_carriers = set(pypsa_df['carrier'].unique())
    for orig_carrier in original_carriers:
        fuel_carrier = map_pypsa_to_fuel_carrier(orig_carrier)
        # Use original carrier color if available, otherwise use default
        if orig_carrier in carrier_colors:
            # Only set if not already set (first one wins for multiple mappings)
            if fuel_carrier not in fuel_based_colors:
                fuel_based_colors[fuel_carrier] = carrier_colors[orig_carrier]
        elif fuel_carrier in default_colors:
            # Use default color if original carrier not in carrier_colors
            if fuel_carrier not in fuel_based_colors:
                fuel_based_colors[fuel_carrier] = default_colors[fuel_carrier]
    
    # Ensure all carriers have colors (use defaults or gray)
    for carrier in all_carriers:
        if carrier not in fuel_based_colors:
            fuel_based_colors[carrier] = default_colors.get(carrier, '#9B59B6')  # Purple default
    
    # Get colors for carriers (use mapped colors, fallback to default if missing)
    pypsa_colors = [fuel_based_colors.get(c, '#9B59B6') for c in all_carriers]  # Purple default
    sienna_colors = [fuel_based_colors.get(c, '#9B59B6') for c in all_carriers]  # Purple default
    
    # Calculate y-axis limits (include load in max calculation)
    ymin = min(pypsa_neg.sum(axis=1).min(), sienna_neg.sum(axis=1).min())
    ymax = max(
        pypsa_pos.sum(axis=1).max(), 
        sienna_pos.sum(axis=1).max(),
        pypsa_load_total.abs().max() if len(pypsa_load_total) > 0 else 0,
        sienna_load_total.abs().max() if len(sienna_load_total) > 0 else 0
    )
    # Add 5% padding to ensure load line is visible
    ymax = ymax * 1.05
    
    # Create side-by-side plots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 6))
    
    # PyPSA plot (left)
    # Plot generators as stacked area (with low zorder so load can be on top)
    area1 = pypsa_pos.plot.area(
        ax=ax1,
        stacked=True,
        legend=False,
        color=pypsa_colors,
        zorder=1  # Low zorder so load line appears on top
    )
    area2 = pypsa_neg.plot.area(
        ax=ax1,
        stacked=True,
        legend=False,
        color=pypsa_colors,
        zorder=1  # Low zorder so load line appears on top
    )
    
    # Plot load as dashed line at the top (absolute demand value, correctly scaled)
    # Plot AFTER area plots to ensure it's on top
    if len(pypsa_load_total) > 0 and pypsa_load_total.abs().sum() > 0:
        # Load is already scaled correctly (load * 100, AC as-is)
        load_values = pypsa_load_total.abs()
        logger.debug(f"Plotting PyPSA load line: {len(load_values)} points, range [{load_values.min():.2f}, {load_values.max():.2f}]")
        
        # Ensure we have matching indices with the balance DataFrame
        if not load_values.index.equals(pypsa_balance.index):
            logger.warning(f"Load index doesn't match balance index. Reindexing...")
            load_values = load_values.reindex(pypsa_balance.index, fill_value=0)
        
        # Plot directly on the axis using the same index as the area plots
        # Use the DataFrame index to ensure proper DateTime handling
        line = ax1.plot(
            pypsa_balance.index,
            load_values.values,
            color='black',
            linestyle='--',
            linewidth=3.0,
            label='Load',
            alpha=1.0,
            zorder=1000,  # Very high zorder to ensure it's on top of everything
            drawstyle='default'
        )
        logger.info(f"✓ PyPSA load line plotted: {len(load_values)} points, range [{load_values.min():.2f}, {load_values.max():.2f}], y-axis range [{ymin:.2f}, {ymax:.2f}]")
    
    # Set y-axis limits AFTER plotting everything
    ax1.set_ylim(ymin, ymax)
    
    ax1.set_title("PyPSA Energy Balance", fontsize=14, fontweight='bold')
    ax1.set_ylabel("Supply (MW)", fontsize=12)
    ax1.set_xlabel("Time", fontsize=12)
    ax1.grid(True, alpha=0.3)
    
    # Sienna plot (right)
    # Plot generators as stacked area (with low zorder so load can be on top)
    area1 = sienna_pos.plot.area(
        ax=ax2,
        stacked=True,
        legend=False,
        color=sienna_colors,
        zorder=1  # Low zorder so load line appears on top
    )
    area2 = sienna_neg.plot.area(
        ax=ax2,
        stacked=True,
        legend=False,
        color=sienna_colors,
        zorder=1  # Low zorder so load line appears on top
    )
    
    # Plot load as dashed line at the top (absolute demand value, correctly scaled)
    # Plot AFTER area plots to ensure it's on top
    if len(sienna_load_total) > 0 and sienna_load_total.abs().sum() > 0:
        # Load is already scaled correctly (load * 100)
        load_values = sienna_load_total.abs()
        logger.debug(f"Plotting Sienna load line: {len(load_values)} points, range [{load_values.min():.2f}, {load_values.max():.2f}]")
        
        # Ensure we have matching indices with the balance DataFrame
        if not load_values.index.equals(sienna_balance.index):
            logger.warning(f"Load index doesn't match balance index. Reindexing...")
            load_values = load_values.reindex(sienna_balance.index, fill_value=0)
        
        # Plot directly on the axis using the same index as the area plots
        # Use the DataFrame index to ensure proper DateTime handling
        line = ax2.plot(
            sienna_balance.index,
            load_values.values,
            color='black',
            linestyle='--',
            linewidth=3.0,
            label='Load',
            alpha=1.0,
            zorder=1000,  # Very high zorder to ensure it's on top of everything
            drawstyle='default'
        )
        logger.info(f"✓ Sienna load line plotted: {len(load_values)} points, range [{load_values.min():.2f}, {load_values.max():.2f}], y-axis range [{ymin:.2f}, {ymax:.2f}]")
    
    # Set y-axis limits AFTER plotting everything
    ax2.set_ylim(ymin, ymax)
    
    ax2.set_title("Sienna Energy Balance", fontsize=14, fontweight='bold')
    ax2.set_ylabel("Supply (MW)", fontsize=12)
    ax2.set_xlabel("Time", fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    # Create shared legend (generators + load)
    import matplotlib.patches as mpatches
    import matplotlib.lines as mlines
    handles = [mpatches.Patch(color=fuel_based_colors.get(c, '#9B59B6'), label=c) for c in all_carriers]
    # Add load line to legend
    load_handle = mlines.Line2D([], [], color='red', linestyle='--', linewidth=2, label='Load')
    handles.append(load_handle)
    legend_labels = all_carriers + ['Load']
    
    # Adjust layout to make room for legend (ensure bottom row is visible)
    plt.tight_layout(rect=[0, 0.12, 1, 1])  # Reserve bottom 12% for legend
    fig.legend(handles, legend_labels, bbox_to_anchor=(0.5, 0.02), loc='lower center', ncol=min(len(legend_labels), 8))
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        logger.info(f"Saved energy balance comparison to {output_file}")
    else:
        plt.show()
    
    return fig, (ax1, ax2)


def extract_sienna_marginal_costs(sienna_json_file):
    """Extract marginal costs from Sienna system JSON file.
    
    This function parses the JSON directly to avoid time_series loading issues.
    
    Parameters:
        sienna_json_file: Path to Sienna system JSON file
        
    Returns:
        dict: Mapping of generator names to (marginal_cost, p_nom, carrier) tuples
    """
    # Use JSON parsing directly to avoid System loading issues with time_series
    return extract_sienna_costs_from_json(sienna_json_file)


def extract_sienna_costs_from_json(json_file):
    """Extract marginal costs directly from JSON file without loading full system.
    
    This is a fallback when System.from_json() fails due to time_series issues.
    
    Parameters:
        json_file: Path to Sienna system JSON file
        
    Returns:
        dict: Mapping of generator names to (marginal_cost, p_nom, carrier) tuples
    """
    import json
    
    json_file = Path(json_file)
    if not json_file.exists():
        raise FileNotFoundError(f"Sienna JSON file not found: {json_file}")
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    costs = {}
    
    # Navigate through the JSON structure to find generators
    # The structure can vary, so we try multiple paths
    try:
        # Try different possible structures
        components = None
        
        # Path 1: data -> data -> components
        if 'data' in data and isinstance(data['data'], dict):
            if 'components' in data['data']:
                components = data['data']['components']
        
        # Path 2: data -> components (direct)
        if components is None and 'components' in data:
            components = data['components']
        
        # Path 3: components at root
        if components is None and 'components' in data.get('data', {}):
            components = data['data']['components']
        
        if components is None:
            logger.warning("Could not find 'components' in JSON. Trying to find generators directly...")
            # Try to find any dict that looks like a generator
            components = []
            def find_generators(obj, path=""):
                if isinstance(obj, dict):
                    comp_type = obj.get('__type__', '') or obj.get('type', '')
                    if any(x in comp_type for x in ['ThermalStandard', 'RenewableDispatch', 'HydroDispatch']):
                        components.append(obj)
                    else:
                        for key, value in obj.items():
                            find_generators(value, f"{path}.{key}")
                elif isinstance(obj, list):
                    for item in obj:
                        find_generators(item, path)
            
            find_generators(data)
        
        if not components:
            raise ValueError("Could not find any generator components in JSON file")
        
        logger.info(f"Found {len(components)} potential generator components")
        
        for component in components:
            # Check if this is a generator type
            component_type = component.get('__type__', '') or component.get('type', '')
            if not any(x in component_type for x in ['ThermalStandard', 'RenewableDispatch', 'HydroDispatch']):
                continue
            
            gen_name = component.get('name', '')
            if not gen_name:
                continue
            
            # Extract marginal cost from operation_cost
            mc = 0.0
            op_cost = component.get('operation_cost')
            if op_cost:
                variable = op_cost.get('variable')
                if variable:
                    value_curve = variable.get('value_curve')
                    if value_curve:
                        # Try to get proportional_term from LinearCurve
                        if 'proportional_term' in value_curve:
                            mc = float(value_curve['proportional_term'])
                        elif 'function_data' in value_curve:
                            func_data = value_curve['function_data']
                            if isinstance(func_data, dict) and 'proportional_term' in func_data:
                                mc = float(func_data['proportional_term'])
            
            # Get capacity
            p_nom = 0.0
            if 'active_power_limits' in component:
                limits = component['active_power_limits']
                if isinstance(limits, dict):
                    if 'max' in limits:
                        p_nom = float(limits['max'])
                    elif 'maximum' in limits:
                        p_nom = float(limits['maximum'])
                elif isinstance(limits, list) and len(limits) >= 2:
                    p_nom = float(limits[1])
            elif 'rating' in component:
                p_nom = float(component['rating'])
            elif 'active_power' in component:
                ap = component['active_power']
                if isinstance(ap, dict) and 'max' in ap:
                    p_nom = float(ap['max'])
            
            # Get carrier
            carrier = 'unknown'
            if 'fuel' in component:
                fuel = component['fuel']
                carrier = str(fuel) if not isinstance(fuel, dict) else str(fuel.get('value', fuel))
            elif 'prime_mover_type' in component:
                pmt = component['prime_mover_type']
                carrier = str(pmt) if not isinstance(pmt, dict) else str(pmt.get('value', pmt))
            
            # Map to PyPSA carrier name
            carrier = map_sienna_to_pypsa_carrier(carrier)
            
            if p_nom > 0:
                costs[gen_name] = (float(mc), float(p_nom), carrier)
        
        logger.info(f"Extracted costs for {len(costs)} generators")
    
    except Exception as e:
        logger.error(f"Error extracting costs from JSON: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    
    return costs


def plot_marginal_costs_comparison_pypsa_only(network_file, carrier_colors, output_file=None):
    """Create PyPSA-only marginal costs visualization (fallback when Sienna data unavailable).
    
    Parameters:
        network_file: Path to PyPSA network file
        carrier_colors: dict mapping carrier names to colors
        output_file: Optional path to save the plot
    """
    network = pypsa.Network(network_file)
    gen_df = network.generators.copy()
    gen_df_sorted = gen_df.sort_values("marginal_cost")
    
    pypsa_p_nom = gen_df_sorted["p_nom"].values / 1000  # Convert to GW
    pypsa_mc = gen_df_sorted["marginal_cost"].replace(0, 3).values
    pypsa_carriers = gen_df_sorted["carrier"].values
    pypsa_lefts = np.concatenate([[0], np.cumsum(pypsa_p_nom)[:-1]])
    
    pypsa_colors = [carrier_colors.get(c, '#808080') for c in pypsa_carriers]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(
        x=pypsa_lefts,
        height=pypsa_mc,
        width=pypsa_p_nom,
        align='edge',
        edgecolor='grey',
        linewidth=0.05,
        color=pypsa_colors
    )
    ax.set_xlabel("Cumulative Generator p_nom (GW)", fontsize=16)
    ax.set_ylabel("Marginal Cost ($/MWh)", fontsize=16)
    ax.set_title("PyPSA Marginal Costs", fontsize=14, fontweight='bold')
    ax.tick_params(axis='x', labelsize=12)
    ax.tick_params(axis='y', labelsize=12)
    ax.grid(True, alpha=0.3)
    
    import matplotlib.patches as mpatches
    unique_carriers, idx = np.unique(pypsa_carriers, return_index=True)
    unique_colors = pypsa_colors[idx]
    handles = [mpatches.Patch(color=color, label=carrier) for carrier, color in zip(unique_carriers, unique_colors)]
    ax.legend(handles=handles, title="Carrier", fontsize=12, title_fontsize=14, loc="center left", bbox_to_anchor=(1.02, 0.5))
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        logger.info(f"Saved PyPSA marginal costs plot to {output_file}")
    
    return fig, ax


def plot_marginal_costs_comparison(network_file, sienna_json_file, carrier_colors, output_file=None):
    """Create side-by-side marginal costs visualization for PyPSA and Sienna.
    
    Parameters:
        network_file: Path to PyPSA network file
        sienna_json_file: Path to Sienna system JSON file
        carrier_colors: dict mapping carrier names to colors
        output_file: Optional path to save the plot
    """
    # Extract PyPSA costs
    network = pypsa.Network(network_file)
    gen_df = network.generators.copy()
    gen_df_sorted = gen_df.sort_values("marginal_cost")
    
    pypsa_p_nom = gen_df_sorted["p_nom"].values / 1000  # Convert to GW
    pypsa_mc = gen_df_sorted["marginal_cost"].replace(0, 3).values
    pypsa_carriers = gen_df_sorted["carrier"].values
    pypsa_lefts = np.concatenate([[0], np.cumsum(pypsa_p_nom)[:-1]])
    
    # Extract Sienna costs
    try:
        sienna_costs = extract_sienna_marginal_costs(sienna_json_file)
    except Exception as e:
        logger.warning(f"Could not extract Sienna marginal costs: {e}")
        logger.warning("Creating PyPSA-only marginal costs plot...")
        # Fall back to PyPSA-only plot
        return plot_marginal_costs_comparison_pypsa_only(network_file, carrier_colors, output_file)
    
    if not sienna_costs:
        logger.warning("No Sienna costs extracted. Creating PyPSA-only plot...")
        return plot_marginal_costs_comparison_pypsa_only(network_file, carrier_colors, output_file)
    
    # Convert to sorted lists
    sienna_data = []
    for gen_name, (mc, p_nom, carrier) in sienna_costs.items():
        sienna_data.append({
            'name': gen_name,
            'marginal_cost': mc if mc != 0 else 3.0,  # Replace 0 with 3 for visibility
            'p_nom': p_nom / 1000,  # Convert to GW
            'carrier': carrier
        })
    
    sienna_df = pd.DataFrame(sienna_data)
    
    if sienna_df.empty:
        logger.warning("Sienna DataFrame is empty. Creating PyPSA-only plot...")
        return plot_marginal_costs_comparison_pypsa_only(network_file, carrier_colors, output_file)
    
    sienna_df_sorted = sienna_df.sort_values("marginal_cost")
    
    sienna_p_nom = sienna_df_sorted["p_nom"].values
    sienna_mc = sienna_df_sorted["marginal_cost"].values
    sienna_carriers = sienna_df_sorted["carrier"].values
    
    if len(sienna_p_nom) == 0:
        logger.warning("No Sienna generators with capacity. Creating PyPSA-only plot...")
        return plot_marginal_costs_comparison_pypsa_only(network_file, carrier_colors, output_file)
    
    sienna_lefts = np.concatenate([[0], np.cumsum(sienna_p_nom)[:-1]])
    
    # Get colors for both systems
    pypsa_colors = [carrier_colors.get(c, '#808080') for c in pypsa_carriers]
    sienna_colors = [carrier_colors.get(c, '#808080') for c in sienna_carriers]
    
    # Create side-by-side plots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 6))
    
    # PyPSA plot (left)
    ax1.bar(
        x=pypsa_lefts,
        height=pypsa_mc,
        width=pypsa_p_nom,
        align='edge',
        edgecolor='grey',
        linewidth=0.05,
        color=pypsa_colors
    )
    ax1.set_xlabel("Cumulative Generator p_nom (GW)", fontsize=16)
    ax1.set_ylabel("Marginal Cost ($/MWh)", fontsize=16)
    ax1.set_title("PyPSA Marginal Costs", fontsize=14, fontweight='bold')
    ax1.tick_params(axis='x', labelsize=12)
    ax1.tick_params(axis='y', labelsize=12)
    ax1.grid(True, alpha=0.3)
    
    # Sienna plot (right)
    ax2.bar(
        x=sienna_lefts,
        height=sienna_mc,
        width=sienna_p_nom,
        align='edge',
        edgecolor='grey',
        linewidth=0.05,
        color=sienna_colors
    )
    ax2.set_xlabel("Cumulative Generator p_nom (GW)", fontsize=16)
    ax2.set_ylabel("Marginal Cost ($/MWh)", fontsize=16)
    ax2.set_title("Sienna Marginal Costs", fontsize=14, fontweight='bold')
    ax2.tick_params(axis='x', labelsize=12)
    ax2.tick_params(axis='y', labelsize=12)
    ax2.grid(True, alpha=0.3)
    
    # Set same y-axis scale for comparison
    ymin = min(pypsa_mc.min(), sienna_mc.min())
    ymax = max(pypsa_mc.max(), sienna_mc.max())
    ax1.set_ylim(ymin, ymax)
    ax2.set_ylim(ymin, ymax)
    
    # Create shared legend
    import matplotlib.patches as mpatches
    all_carriers = sorted(set(pypsa_carriers) | set(sienna_carriers))
    handles = [mpatches.Patch(color=carrier_colors.get(c, '#808080'), label=c) for c in all_carriers]
    fig.legend(handles, all_carriers, bbox_to_anchor=(0.5, -0.05), loc='lower center', ncol=min(len(all_carriers), 8))
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        logger.info(f"Saved marginal costs comparison to {output_file}")
    
    return fig, (ax1, ax2)


def main():
    """Main function to run comparison."""
    parser = argparse.ArgumentParser(description='Compare PyPSA and Sienna dispatch results visually')
    parser.add_argument(
        '--pypsa-dispatch',
        type=str,
        default='tests/test_output/pypsa_dispatch.csv',
        help='Path to PyPSA dispatch CSV file'
    )
    parser.add_argument(
        '--sienna-dispatch',
        type=str,
        default='tests/test_output/sienna_dispatch.csv',
        help='Path to Sienna dispatch CSV file'
    )
    parser.add_argument(
        '--network-file',
        type=str,
        default='tests/data/test_network_1h.nc',
        help='Path to PyPSA network file (for carrier colors)'
    )
    parser.add_argument(
        '--sienna-json',
        type=str,
        default='tests/test_output/test_network_1h_output_optimized.json',
        help='Path to Sienna system JSON file (for marginal costs)'
    )
    parser.add_argument(
        '--timesteps',
        type=int,
        default=168,
        help='Number of timesteps to plot (default: 168 for 1 week)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='tests/test_output',
        help='Output directory for saved plots'
    )
    parser.add_argument(
        '--no-show',
        action='store_true',
        help='Do not display plots interactively (only save)'
    )
    
    args = parser.parse_args()
    
    # Load data
    logger.info("Loading PyPSA dispatch data...")
    pypsa_df = load_pypsa_dispatch(args.pypsa_dispatch)
    logger.info(f"Loaded {len(pypsa_df)} PyPSA dispatch records")
    
    logger.info("Loading Sienna dispatch data...")
    sienna_df = load_sienna_dispatch(args.sienna_dispatch)
    logger.info(f"Loaded {len(sienna_df)} Sienna dispatch records")
    
    logger.info("Loading PyPSA network for carrier colors...")
    carrier_colors = get_carrier_colors(args.network_file)
    logger.info(f"Loaded colors for {len(carrier_colors)} carriers")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create side-by-side energy balance plots
    logger.info("Creating side-by-side energy balance plots...")
    energy_balance_file = output_dir / "dispatch_comparison_energy_balance.png"
    plot_side_by_side_energy_balance(
        pypsa_df, sienna_df, carrier_colors,
        timesteps=args.timesteps,
        output_file=str(energy_balance_file)
    )
    # Always close the plot (don't show interactively)
    plt.close()
    
    # # Create marginal costs plot
    # logger.info("Creating marginal costs comparison plot...")
    # marginal_costs_file = output_dir / "dispatch_comparison_marginal_costs.png"
    # plot_marginal_costs_comparison(
    #     args.network_file,
    #     args.sienna_json,
    #     carrier_colors,
    #     output_file=str(marginal_costs_file)
    # )
    # if not args.no_show:
    #     plt.show()
    # else:
    #     plt.close()
    
    logger.info("Comparison complete!")


if __name__ == "__main__":
    main()

