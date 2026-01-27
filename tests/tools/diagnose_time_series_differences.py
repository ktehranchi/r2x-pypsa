"""Compare time series values between PyPSA and Sienna to find differences.

This script checks if the capacity factor time series values differ between
PyPSA and Sienna, which could explain dispatch differences.
"""

import pypsa
import pandas as pd
import json
import h5py
import sqlite3
from pathlib import Path
from loguru import logger
import numpy as np

def compare_time_series_values():
    """Compare actual time series values between PyPSA and Sienna."""
    
    # Paths
    test_file = Path("tests/data/test_network_1h.nc")
    json_file = Path("tests/test_output/test_network_1h_comparison.json")
    h5_file = Path("tests/test_output/test_network_1h_comparison.h5")
    
    logger.info("=" * 80)
    logger.info("TIME SERIES VALUE COMPARISON")
    logger.info("=" * 80)
    
    # Load PyPSA network
    network = pypsa.Network(test_file)
    
    # Apply same modifications as in test
    for component in network.components.keys():
        for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
            if attr in network.df(component).columns:
                network.df(component)[attr] = False
    
    # Get renewable generators
    renewable_carriers = ['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'hydro', 'ror']
    pypsa_renewables = network.generators[
        (network.generators.carrier.isin(renewable_carriers)) & 
        (network.generators.p_nom > 0)
    ].copy()
    
    # Load Sienna data
    with open(json_file) as f:
        sienna_data = json.load(f)
    
    components = sienna_data.get('data', {}).get('components', [])
    sienna_renewables = {
        g.get('name'): g
        for g in components
        if g.get('__metadata__', {}).get('type') == 'RenewableDispatch'
    }
    
    # Compare time series for matching generators
    logger.info(f"\nComparing time series for {len(pypsa_renewables)} generators...")
    
    if not h5_file.exists():
        logger.error(f"HDF5 file not found: {h5_file}")
        return
    
    # Extract Sienna time series metadata
    with h5py.File(h5_file, 'r') as h5:
        if 'time_series_metadata' not in h5:
            logger.error("No time_series_metadata in HDF5 file")
            return
        
        db_data = h5['time_series_metadata'][()]
        db_path = Path(".temp_ts_comparison.db")
        
        with open(db_path, 'wb') as db_file:
            db_file.write(bytes(db_data))
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        table_name = 'time_series_metadata' if 'time_series_metadata' in tables else 'time_series_associations'
        
        # Compare each generator
        differences = []
        max_diffs = []
        mean_diffs = []
        
        # Limit to first 168 timesteps (1 week) for comparison
        snapshots = network.snapshots[:168] if len(network.snapshots) >= 168 else network.snapshots
        
        for gen_name in pypsa_renewables.index:  # Compare all generators
            if gen_name not in sienna_renewables:
                continue
            
            gen = pypsa_renewables.loc[gen_name]
            p_nom = gen.p_nom
            
            # Get PyPSA time series
            if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_max_pu'):
                if gen_name in network.generators_t.p_max_pu.columns:
                    pypsa_ts = network.generators_t.p_max_pu[gen_name].loc[snapshots]
                    pypsa_available = (pypsa_ts * p_nom).values  # MW available
                else:
                    continue
            else:
                continue
            
            # Get Sienna time series
            sienna_gen = sienna_renewables[gen_name]
            gen_uuid = sienna_gen.get('internal', {}).get('uuid', {}).get('value')
            if not gen_uuid:
                continue
            
            query = f'''
                SELECT time_series_uuid, initial_timestamp, resolution, length
                FROM {table_name}
                WHERE owner_uuid = ? AND owner_type = 'RenewableDispatch' AND name = 'max_active_power'
            '''
            cursor.execute(query, (gen_uuid,))
            result = cursor.fetchone()
            
            if not result:
                continue
            
            ts_uuid, initial_timestamp, resolution, length = result
            
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
            
            if ts_data is None:
                continue
            
            # Convert Sienna time series to MW
            base_power = sienna_gen.get('base_power', 0.0)
            rating = sienna_gen.get('rating', 0.0)
            power_factor = sienna_gen.get('power_factor', 1.0)
            max_active_power = rating * base_power * power_factor
            
            # Time series is in per-unit (0-1), convert to MW
            sienna_ts_pu = ts_data[:len(snapshots)]  # Limit to same length
            sienna_available = (sienna_ts_pu * max_active_power)[:len(snapshots)]
            
            # Compare
            if len(pypsa_available) != len(sienna_available):
                min_len = min(len(pypsa_available), len(sienna_available))
                pypsa_available = pypsa_available[:min_len]
                sienna_available = sienna_available[:min_len]
            
            if len(pypsa_available) == 0:
                continue
            
            # Calculate differences
            diff = pypsa_available - sienna_available
            max_diff = np.max(np.abs(diff))
            mean_diff = np.mean(np.abs(diff))
            total_diff = np.sum(diff)
            
            differences.append({
                'name': gen_name,
                'carrier': gen.carrier,
                'p_nom': p_nom,
                'max_diff': max_diff,
                'mean_diff': mean_diff,
                'total_diff': total_diff,
                'pypsa_total': np.sum(pypsa_available),
                'sienna_total': np.sum(sienna_available),
            })
            
            max_diffs.append(max_diff)
            mean_diffs.append(mean_diff)
            
            if max_diff > 0.1:  # Significant difference
                logger.warning(
                    f"{gen_name} ({gen.carrier}): "
                    f"max_diff={max_diff:.4f} MW, mean_diff={mean_diff:.4f} MW, "
                    f"total_diff={total_diff:.2f} MWh"
                )
        
        conn.close()
        db_path.unlink()
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Compared {len(differences)} generators")
    if differences:
        logger.info(f"Max difference across all generators: {max(max_diffs):.4f} MW")
        logger.info(f"Mean difference across all generators: {np.mean(mean_diffs):.4f} MW")
        
        total_pypsa = sum(d['pypsa_total'] for d in differences)
        total_sienna = sum(d['sienna_total'] for d in differences)
        total_diff = total_pypsa - total_sienna
        
        logger.info(f"\nTotal available generation (first 168 timesteps):")
        logger.info(f"  PyPSA: {total_pypsa:.2f} MWh")
        logger.info(f"  Sienna: {total_sienna:.2f} MWh")
        logger.info(f"  Difference: {total_diff:.2f} MWh")
        
        # Sort by total difference
        differences_sorted = sorted(differences, key=lambda x: abs(x['total_diff']), reverse=True)
        
        # Group by carrier for summary
        by_carrier = {}
        for d in differences:
            carrier = d['carrier']
            if carrier not in by_carrier:
                by_carrier[carrier] = {
                    'count': 0,
                    'total_pypsa': 0.0,
                    'total_sienna': 0.0,
                    'total_diff': 0.0,
                    'max_diff': 0.0,
                    'mean_diff': 0.0
                }
            by_carrier[carrier]['count'] += 1
            by_carrier[carrier]['total_pypsa'] += d['pypsa_total']
            by_carrier[carrier]['total_sienna'] += d['sienna_total']
            by_carrier[carrier]['total_diff'] += d['total_diff']
            by_carrier[carrier]['max_diff'] = max(by_carrier[carrier]['max_diff'], d['max_diff'])
            by_carrier[carrier]['mean_diff'] += d['mean_diff']
        
        # Calculate mean differences
        for carrier in by_carrier:
            if by_carrier[carrier]['count'] > 0:
                by_carrier[carrier]['mean_diff'] /= by_carrier[carrier]['count']
        
        logger.info(f"\nSummary by carrier:")
        logger.info(f"{'Carrier':<15} {'Count':<8} {'PyPSA Total':<15} {'Sienna Total':<15} {'Diff (MWh)':<15} {'Max Diff (MW)':<15} {'Mean Diff (MW)':<15}")
        logger.info("-" * 98)
        for carrier in sorted(by_carrier.keys()):
            d = by_carrier[carrier]
            logger.info(
                f"{carrier:<15} {d['count']:<8} "
                f"{d['total_pypsa']:>14.2f} {d['total_sienna']:>14.2f} "
                f"{d['total_diff']:>14.2f} {d['max_diff']:>14.4f} {d['mean_diff']:>14.4f}"
            )
        
        logger.info(f"\nTop 20 generators by total difference:")
        logger.info(f"{'Name':<30} {'Carrier':<10} {'PyPSA Total':<15} {'Sienna Total':<15} {'Diff (MWh)':<15} {'Max Diff (MW)':<15}")
        logger.info("-" * 100)
        for d in differences_sorted[:20]:
            logger.info(
                f"{d['name']:<30} {d['carrier']:<10} "
                f"{d['pypsa_total']:>14.2f} {d['sienna_total']:>14.2f} "
                f"{d['total_diff']:>14.2f} {d['max_diff']:>14.4f}"
            )
        
        # Count generators with significant differences
        significant_diffs = [d for d in differences if abs(d['total_diff']) > 1.0]  # > 1 MWh difference
        logger.info(f"\nGenerators with significant differences (>1 MWh): {len(significant_diffs)}/{len(differences)}")
        
        if significant_diffs:
            logger.info(f"Total difference from significant generators: {sum(d['total_diff'] for d in significant_diffs):.2f} MWh")
    
    logger.info("=" * 80)

if __name__ == "__main__":
    compare_time_series_values()

