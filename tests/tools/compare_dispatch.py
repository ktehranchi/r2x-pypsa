#!/usr/bin/env python3
"""Compare PyPSA and Sienna dispatch results in detail."""

import pypsa
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
from loguru import logger

def load_pypsa_dispatch(network_file, output_dir, optimize_if_needed=True):
    """Load PyPSA dispatch results after optimization."""
    network = pypsa.Network(network_file)
    
    # Check if network has been optimized
    if network.objective is None:
        if optimize_if_needed:
            logger.info("Network has not been optimized. Running optimization...")
            # Set all capital costs to zero for pure economic dispatch
            for component_type in ['Generator', 'StorageUnit', 'Store', 'Link', 'Line']:
                if component_type in network.components.keys():
                    df = network.df(component_type)
                    if 'capital_cost' in df.columns:
                        df['capital_cost'] = 0.0
                    if 'p_nom_extendable' in df.columns:
                        df['p_nom_extendable'] = False
                    if 's_nom_extendable' in df.columns:
                        df['s_nom_extendable'] = False
                    if 'e_nom_extendable' in df.columns:
                        df['e_nom_extendable'] = False
            
            # Optimize for 1 week
            network.optimize(
                snapshots=network.snapshots[0:7*24],
                solver_name='gurobi'
            )
            logger.info(f"Optimization completed. Objective: {network.objective:,.2f}")
        else:
            logger.warning("Network has not been optimized. Run optimization first.")
            return None
    
    # Get generator dispatch (in MW)
    if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
        gen_dispatch = network.generators_t.p.copy()
    else:
        logger.warning("No generator dispatch data found")
        return None
    
    # Get storage dispatch
    storage_dispatch = {}
    if hasattr(network, 'storage_units_t') and hasattr(network.storage_units_t, 'p'):
        storage_dispatch['discharge'] = network.storage_units_t.p.clip(lower=0)  # Positive = discharge
        storage_dispatch['charge'] = network.storage_units_t.p.clip(upper=0).abs()  # Negative = charge
    
    # Get marginal costs
    marginal_costs = network.generators['marginal_cost'].to_dict()
    
    # Calculate costs (marginal_cost * generation)
    gen_costs = gen_dispatch.copy()
    for gen_name in gen_costs.columns:
        if gen_name in marginal_costs:
            gen_costs[gen_name] = gen_costs[gen_name] * marginal_costs[gen_name]
        else:
            gen_costs[gen_name] = 0.0
    
    return {
        'generation': gen_dispatch,
        'costs': gen_costs,
        'marginal_costs': marginal_costs,
        'storage': storage_dispatch,
        'network': network,
    }


def load_sienna_dispatch(dispatch_file):
    """Load Sienna dispatch results from CSV."""
    if not dispatch_file.exists():
        logger.error(f"Sienna dispatch file not found: {dispatch_file}")
        return None
    
    df = pd.read_csv(dispatch_file)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    
    # Pivot to get generation by generator and timestep
    # The CSV has: DateTime, carrier, value
    # We need to group by generator name, but the CSV only has carrier
    # Let's create a summary by carrier first, then we'll need to match generators
    
    # For now, let's pivot by carrier and DateTime
    dispatch_pivot = df.pivot_table(
        index='DateTime',
        columns='carrier',
        values='value',
        aggfunc='sum',
        fill_value=0.0
    )
    
    return {
        'dispatch': df,
        'by_carrier': dispatch_pivot,
    }


def match_generators(pypsa_data, sienna_data):
    """Match generators between PyPSA and Sienna systems."""
    network = pypsa_data['network']
    sienna_dispatch = sienna_data['dispatch']
    
    # Get PyPSA generators with their carriers
    pypsa_gens = network.generators[['carrier', 'marginal_cost', 'p_nom']].copy()
    pypsa_gens.index.name = 'generator'
    pypsa_gens = pypsa_gens.reset_index()
    
    # Get unique carriers from Sienna
    sienna_carriers = sienna_dispatch['carrier'].unique()
    
    # Match by carrier
    matches = []
    for carrier in sienna_carriers:
        pypsa_carrier_gens = pypsa_gens[pypsa_gens['carrier'] == carrier]
        if len(pypsa_carrier_gens) > 0:
            matches.append({
                'carrier': carrier,
                'pypsa_generators': pypsa_carrier_gens['generator'].tolist(),
                'pypsa_count': len(pypsa_carrier_gens),
                'total_p_nom': pypsa_carrier_gens['p_nom'].sum(),
            })
    
    return matches


def compare_dispatch_by_carrier(pypsa_data, sienna_data, timesteps=None):
    """Compare dispatch aggregated by carrier."""
    network = pypsa_data['network']
    pypsa_gen = pypsa_data['generation']
    pypsa_costs = pypsa_data['costs']
    sienna_by_carrier = sienna_data['by_carrier']
    
    # Limit timesteps if specified
    if timesteps is not None:
        pypsa_gen = pypsa_gen.iloc[:timesteps]
        pypsa_costs = pypsa_costs.iloc[:timesteps]
        sienna_by_carrier = sienna_by_carrier.iloc[:timesteps]
    
    # Aggregate PyPSA by carrier
    pypsa_by_carrier_gen = pd.DataFrame(index=pypsa_gen.index)
    pypsa_by_carrier_costs = pd.DataFrame(index=pypsa_costs.index)
    
    for carrier in network.generators['carrier'].unique():
        carrier_gens = network.generators[network.generators['carrier'] == carrier].index
        if len(carrier_gens) > 0:
            pypsa_by_carrier_gen[carrier] = pypsa_gen[carrier_gens].sum(axis=1)
            pypsa_by_carrier_costs[carrier] = pypsa_costs[carrier_gens].sum(axis=1)
    
    # Compare
    comparison = pd.DataFrame()
    
    # Get common carriers
    common_carriers = set(pypsa_by_carrier_gen.columns) & set(sienna_by_carrier.columns)
    
    for carrier in common_carriers:
        pypsa_gen_total = pypsa_by_carrier_gen[carrier].sum()
        sienna_gen_total = sienna_by_carrier[carrier].sum()
        pypsa_cost_total = pypsa_by_carrier_costs[carrier].sum()
        
        # Estimate Sienna cost (we don't have per-generator costs, so use average)
        # For now, just report generation differences
        gen_diff = pypsa_gen_total - sienna_gen_total
        gen_diff_pct = (gen_diff / pypsa_gen_total * 100) if pypsa_gen_total != 0 else 0
        
        comparison = pd.concat([comparison, pd.DataFrame({
            'carrier': [carrier],
            'pypsa_generation_mwh': [pypsa_gen_total],
            'sienna_generation_mwh': [sienna_gen_total],
            'generation_diff_mwh': [gen_diff],
            'generation_diff_pct': [gen_diff_pct],
            'pypsa_cost_usd': [pypsa_cost_total],
        })], ignore_index=True)
    
    return comparison.sort_values('generation_diff_mwh', key=abs, ascending=False)


def compare_detailed(pypsa_data, sienna_data, output_dir, timesteps=None):
    """Create detailed comparison report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    network = pypsa_data['network']
    pypsa_gen = pypsa_data['generation']
    pypsa_costs = pypsa_data['costs']
    
    # Limit timesteps
    if timesteps is not None:
        pypsa_gen = pypsa_gen.iloc[:timesteps]
        pypsa_costs = pypsa_costs.iloc[:timesteps]
    
    # 1. Compare by carrier
    print("\n" + "=" * 80)
    print("DISPATCH COMPARISON BY CARRIER")
    print("=" * 80)
    carrier_comparison = compare_dispatch_by_carrier(pypsa_data, sienna_data, timesteps)
    print(carrier_comparison.to_string(index=False))
    
    # Save to CSV
    carrier_file = output_dir / "dispatch_comparison_by_carrier.csv"
    carrier_comparison.to_csv(carrier_file, index=False)
    print(f"\n✓ Saved carrier comparison to: {carrier_file}")
    
    # 2. Time series comparison for top carriers
    print("\n" + "=" * 80)
    print("TIME SERIES COMPARISON (Top 5 carriers by difference)")
    print("=" * 80)
    
    top_carriers = carrier_comparison.head(5)['carrier'].tolist()
    sienna_by_carrier = sienna_data['by_carrier']
    
    if timesteps is not None:
        sienna_by_carrier = sienna_by_carrier.iloc[:timesteps]
    
    # Aggregate PyPSA by carrier
    pypsa_by_carrier = pd.DataFrame(index=pypsa_gen.index)
    for carrier in network.generators['carrier'].unique():
        carrier_gens = network.generators[network.generators['carrier'] == carrier].index
        if len(carrier_gens) > 0:
            pypsa_by_carrier[carrier] = pypsa_gen[carrier_gens].sum(axis=1)
    
    # Plot time series for top carriers
    fig, axes = plt.subplots(len(top_carriers), 1, figsize=(14, 3*len(top_carriers)))
    if len(top_carriers) == 1:
        axes = [axes]
    
    for idx, carrier in enumerate(top_carriers):
        ax = axes[idx]
        if carrier in pypsa_by_carrier.columns and carrier in sienna_by_carrier.columns:
            pypsa_ts = pypsa_by_carrier[carrier]
            sienna_ts = sienna_by_carrier[carrier]
            
            # Ensure indices are compatible (use integer positions for plotting)
            pypsa_values = pypsa_ts.values.flatten() if hasattr(pypsa_ts.values, 'flatten') else pypsa_ts.values
            sienna_values = sienna_ts.values.flatten() if hasattr(sienna_ts.values, 'flatten') else sienna_ts.values
            
            # Use integer x-axis
            x_axis = range(len(pypsa_ts))
            
            ax.plot(x_axis, pypsa_values, label='PyPSA', alpha=0.7, linewidth=1.5)
            ax.plot(x_axis, sienna_values, label='Sienna', alpha=0.7, linewidth=1.5)
            ax.set_title(f'{carrier} Dispatch Comparison')
            ax.set_xlabel('Time')
            ax.set_ylabel('Generation (MW)')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # Calculate and display statistics (align by position, not index)
            min_len = min(len(pypsa_ts), len(sienna_ts))
            pypsa_aligned = pypsa_values[:min_len]
            sienna_aligned = sienna_values[:min_len]
            gen_diff = np.abs(pypsa_aligned - sienna_aligned).sum()
            gen_diff_pct = (gen_diff / pypsa_aligned.sum() * 100) if pypsa_aligned.sum() != 0 else 0
            ax.text(0.02, 0.98, f'Total diff: {gen_diff:.1f} MWh ({gen_diff_pct:.2f}%)',
                   transform=ax.transAxes, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plot_file = output_dir / "dispatch_comparison_timeseries.png"
    plt.savefig(plot_file, dpi=150, bbox_inches='tight')
    print(f"✓ Saved time series plot to: {plot_file}")
    plt.close()
    
    # 3. Cost comparison
    print("\n" + "=" * 80)
    print("COST COMPARISON BY CARRIER")
    print("=" * 80)
    
    pypsa_by_carrier_costs = pd.DataFrame(index=pypsa_costs.index)
    for carrier in network.generators['carrier'].unique():
        carrier_gens = network.generators[network.generators['carrier'] == carrier].index
        if len(carrier_gens) > 0:
            pypsa_by_carrier_costs[carrier] = pypsa_costs[carrier_gens].sum(axis=1)
    
    cost_summary = pd.DataFrame({
        'carrier': pypsa_by_carrier_costs.columns,
        'total_cost_usd': pypsa_by_carrier_costs.sum().values,
    }).sort_values('total_cost_usd', ascending=False)
    
    print(cost_summary.to_string(index=False))
    
    cost_file = output_dir / "cost_comparison_by_carrier.csv"
    cost_summary.to_csv(cost_file, index=False)
    print(f"\n✓ Saved cost comparison to: {cost_file}")
    
    # 4. Per-generator comparison (for generators that exist in both systems)
    print("\n" + "=" * 80)
    print("PER-GENERATOR COMPARISON (Top 20 by generation difference)")
    print("=" * 80)
    
    # Note: Sienna only exports by carrier, not by individual generator
    # So we can't do true per-generator comparison without modifying the Julia script
    # For now, show PyPSA generators with highest/lowest dispatch
    gen_totals = pypsa_gen.sum().sort_values(ascending=False)
    gen_costs_totals = pypsa_costs.sum().sort_values(ascending=False)
    
    print("\nTop 20 PyPSA generators by total generation:")
    top_gens = gen_totals.head(20)
    for gen_name in top_gens.index:
        gen = network.generators.loc[gen_name]
        total_gen = gen_totals[gen_name]
        total_cost = gen_costs_totals.get(gen_name, 0.0)
        mc = gen.get('marginal_cost', 0.0)
        print(f"  {gen_name:30s} | {gen.carrier:10s} | {total_gen:12.2f} MWh | ${mc:8.2f}/MWh | ${total_cost:12.2f}")
    
    # Save per-generator summary
    gen_summary = pd.DataFrame({
        'generator': gen_totals.index,
        'carrier': [network.generators.loc[g, 'carrier'] for g in gen_totals.index],
        'total_generation_mwh': gen_totals.values,
        'marginal_cost_usd_per_mwh': [network.generators.loc[g, 'marginal_cost'] for g in gen_totals.index],
        'total_cost_usd': [gen_costs_totals.get(g, 0.0) for g in gen_totals.index],
    })
    
    gen_file = output_dir / "pypsa_generators_summary.csv"
    gen_summary.to_csv(gen_file, index=False)
    print(f"\n✓ Saved per-generator summary to: {gen_file}")
    
    # 5. Key finding: Hydro dispatch difference
    if 'hydro' in carrier_comparison['carrier'].values:
        hydro_row = carrier_comparison[carrier_comparison['carrier'] == 'hydro'].iloc[0]
        print("\n" + "=" * 80)
        print("⚠️  KEY FINDING: HYDRO DISPATCH DIFFERENCE")
        print("=" * 80)
        print(f"PyPSA hydro generation: {hydro_row['pypsa_generation_mwh']:,.2f} MWh")
        print(f"Sienna hydro generation: {hydro_row['sienna_generation_mwh']:,.2f} MWh")
        print(f"Difference: {hydro_row['generation_diff_mwh']:,.2f} MWh ({hydro_row['generation_diff_pct']:.2f}%)")
        print("\nThis large difference in hydro dispatch is likely a major source of the objective difference.")
        print("Possible causes:")
        print("  - Different hydro constraints (water availability, ramping)")
        print("  - Different hydro cost modeling")
        print("  - Different time series data")
    
    return {
        'carrier_comparison': carrier_comparison,
        'cost_summary': cost_summary,
        'generator_summary': gen_summary,
    }


def main():
    """Main comparison function."""
    test_file = Path("tests/data/test_network_1h.nc")
    output_dir = Path("tests/test_output")
    sienna_dispatch_file = output_dir / "sienna_dispatch.csv"
    
    # Load PyPSA dispatch (will optimize if needed)
    logger.info("Loading PyPSA dispatch...")
    pypsa_data = load_pypsa_dispatch(test_file, output_dir, optimize_if_needed=True)
    if pypsa_data is None:
        logger.error("Failed to load PyPSA dispatch.")
        return
    
    # Load Sienna dispatch
    logger.info("Loading Sienna dispatch...")
    sienna_data = load_sienna_dispatch(sienna_dispatch_file)
    if sienna_data is None:
        return
    
    # Compare (use 1 week = 168 hours)
    logger.info("Comparing dispatch...")
    results = compare_detailed(pypsa_data, sienna_data, output_dir, timesteps=7*24)
    
    print("\n" + "=" * 80)
    print("COMPARISON COMPLETE")
    print("=" * 80)
    print(f"Results saved to: {output_dir}")


if __name__ == "__main__":
    main()

