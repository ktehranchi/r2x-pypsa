"""Compare dispatch values for each generator between PyPSA and Sienna.

This script compares the actual dispatch (generation) for each renewable generator
to identify which generators are being dispatched differently.
"""

import pandas as pd
from pathlib import Path
from loguru import logger
import numpy as np

def compare_dispatch_values():
    """Compare actual dispatch values for each generator between PyPSA and Sienna."""
    
    # Paths
    pypsa_dispatch_file = Path("tests/test_output/pypsa_dispatch.csv")
    sienna_dispatch_file = Path("tests/test_output/sienna_dispatch.csv")
    
    logger.info("=" * 80)
    logger.info("DISPATCH VALUE COMPARISON BY GENERATOR")
    logger.info("=" * 80)
    
    if not pypsa_dispatch_file.exists():
        logger.error(f"PyPSA dispatch file not found: {pypsa_dispatch_file}")
        return
    
    if not sienna_dispatch_file.exists():
        logger.error(f"Sienna dispatch file not found: {sienna_dispatch_file}")
        return
    
    # Load dispatch data
    logger.info("Loading dispatch data...")
    pypsa_df = pd.read_csv(pypsa_dispatch_file)
    sienna_df = pd.read_csv(sienna_dispatch_file)
    
    # Convert DateTime to datetime
    pypsa_df['DateTime'] = pd.to_datetime(pypsa_df['DateTime'], errors='coerce')
    sienna_df['DateTime'] = pd.to_datetime(sienna_df['DateTime'], errors='coerce')
    
    # Filter renewables
    renewable_carriers = ['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'hydro', 'ror']
    pypsa_renewables = pypsa_df[pypsa_df['carrier'].isin(renewable_carriers)].copy()
    
    # Map Sienna carriers to PyPSA names
    def map_sienna_to_pypsa(carrier):
        mapping = {
            'PVe': 'solar',
            'WT': 'onwind',
            'WS': 'offwind',
            'HY': 'hydro'
        }
        return mapping.get(carrier, carrier)
    
    sienna_df_mapped = sienna_df.copy()
    sienna_df_mapped['carrier'] = sienna_df_mapped['carrier'].apply(map_sienna_to_pypsa)
    sienna_renewables = sienna_df_mapped[sienna_df_mapped['carrier'].isin(renewable_carriers)].copy()
    
    logger.info(f"PyPSA renewable dispatch records: {len(pypsa_renewables)}")
    logger.info(f"Sienna renewable dispatch records: {len(sienna_renewables)}")
    
    # Get unique generator names
    pypsa_gen_names = set(pypsa_renewables['name'].unique())
    sienna_gen_names = set(sienna_renewables['name'].unique())
    
    logger.info(f"PyPSA renewable generators: {len(pypsa_gen_names)}")
    logger.info(f"Sienna renewable generators: {len(sienna_gen_names)}")
    
    # Find common generators
    common_gens = pypsa_gen_names & sienna_gen_names
    missing_in_sienna = pypsa_gen_names - sienna_gen_names
    missing_in_pypsa = sienna_gen_names - pypsa_gen_names
    
    logger.info(f"Common generators: {len(common_gens)}")
    if missing_in_sienna:
        logger.warning(f"Generators in PyPSA but not in Sienna: {len(missing_in_sienna)}")
        for gen_name in sorted(missing_in_sienna)[:10]:
            logger.warning(f"  - {gen_name}")
    if missing_in_pypsa:
        logger.warning(f"Generators in Sienna but not in PyPSA: {len(missing_in_pypsa)}")
        for gen_name in sorted(missing_in_pypsa)[:10]:
            logger.warning(f"  - {gen_name}")
    
    # Compare dispatch for each common generator
    logger.info(f"\nComparing dispatch for {len(common_gens)} generators...")
    
    differences = []
    
    for gen_name in common_gens:
        # Get PyPSA dispatch for this generator
        pypsa_gen = pypsa_renewables[pypsa_renewables['name'] == gen_name].copy()
        pypsa_gen = pypsa_gen.sort_values('DateTime').reset_index(drop=True)
        
        # Get Sienna dispatch for this generator
        sienna_gen = sienna_renewables[sienna_renewables['name'] == gen_name].copy()
        sienna_gen = sienna_gen.sort_values('DateTime').reset_index(drop=True)
        
        if len(pypsa_gen) == 0 or len(sienna_gen) == 0:
            continue
        
        # Get carrier (should be same for both)
        carrier = pypsa_gen['carrier'].iloc[0] if len(pypsa_gen) > 0 else 'unknown'
        
        # Sum total dispatch
        pypsa_total = pypsa_gen['value'].sum()
        sienna_total = sienna_gen['value'].sum()
        total_diff = pypsa_total - sienna_total
        
        # Calculate per-timestep differences (align by position, not timestamp)
        min_len = min(len(pypsa_gen), len(sienna_gen))
        if min_len > 0:
            pypsa_values = pypsa_gen['value'].values[:min_len]
            sienna_values = sienna_gen['value'].values[:min_len]
            
            diff_values = pypsa_values - sienna_values
            max_diff = np.max(np.abs(diff_values))
            mean_diff = np.mean(np.abs(diff_values))
            
            differences.append({
                'name': gen_name,
                'carrier': carrier,
                'pypsa_total': pypsa_total,
                'sienna_total': sienna_total,
                'total_diff': total_diff,
                'max_diff': max_diff,
                'mean_diff': mean_diff,
                'num_timesteps': min_len
            })
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Compared {len(differences)} generators")
    
    if differences:
        # Overall statistics
        total_pypsa = sum(d['pypsa_total'] for d in differences)
        total_sienna = sum(d['sienna_total'] for d in differences)
        total_diff = total_pypsa - total_sienna
        
        logger.info(f"\nTotal dispatch (all generators):")
        logger.info(f"  PyPSA: {total_pypsa:.2f} MWh")
        logger.info(f"  Sienna: {total_sienna:.2f} MWh")
        logger.info(f"  Difference: {total_diff:.2f} MWh")
        
        # Group by carrier
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
        
        # Sort by absolute total difference
        differences_sorted = sorted(differences, key=lambda x: abs(x['total_diff']), reverse=True)
        
        logger.info(f"\nTop 30 generators by total dispatch difference:")
        logger.info(f"{'Name':<35} {'Carrier':<10} {'PyPSA (MWh)':<15} {'Sienna (MWh)':<15} {'Diff (MWh)':<15} {'Max Diff (MW)':<15} {'Mean Diff (MW)':<15}")
        logger.info("-" * 120)
        for d in differences_sorted[:30]:
            logger.info(
                f"{d['name']:<35} {d['carrier']:<10} "
                f"{d['pypsa_total']:>14.2f} {d['sienna_total']:>14.2f} "
                f"{d['total_diff']:>14.2f} {d['max_diff']:>14.4f} {d['mean_diff']:>14.4f}"
            )
        
        # Count generators with significant differences
        significant_diffs = [d for d in differences if abs(d['total_diff']) > 1.0]  # > 1 MWh difference
        logger.info(f"\nGenerators with significant differences (>1 MWh): {len(significant_diffs)}/{len(differences)}")
        
        if significant_diffs:
            sig_total_diff = sum(d['total_diff'] for d in significant_diffs)
            logger.info(f"Total difference from significant generators: {sig_total_diff:.2f} MWh")
            logger.info(f"Percentage of total difference: {abs(sig_total_diff / total_diff * 100):.2f}%")
        
        # Count generators with zero dispatch in one but not the other
        zero_dispatch_issues = []
        for d in differences:
            if (d['pypsa_total'] == 0 and d['sienna_total'] > 0.01) or \
               (d['sienna_total'] == 0 and d['pypsa_total'] > 0.01):
                zero_dispatch_issues.append(d)
        
        if zero_dispatch_issues:
            logger.warning(f"\n⚠️  Generators with zero dispatch in one system but not the other: {len(zero_dispatch_issues)}")
            for d in zero_dispatch_issues[:10]:
                logger.warning(
                    f"  {d['name']} ({d['carrier']}): "
                    f"PyPSA={d['pypsa_total']:.2f} MWh, Sienna={d['sienna_total']:.2f} MWh"
                )
    
    logger.info("=" * 80)

if __name__ == "__main__":
    compare_dispatch_values()

