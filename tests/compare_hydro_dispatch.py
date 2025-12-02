"""Compare PyPSA and Sienna hydro dispatch side-by-side."""

import pypsa
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Optional


def load_pypsa_hydro_dispatch_from_file(
    dispatch_file: str | Path,
) -> pd.DataFrame:
    """Load PyPSA hydro dispatch from saved CSV file.
    
    Parameters
    ----------
    dispatch_file : str | Path
        Path to pypsa_hydro_per_generator.csv
        
    Returns
    -------
    pd.DataFrame
        DataFrame with columns: DateTime, name, value (MW)
    """
    df = pd.read_csv(dispatch_file, parse_dates=['DateTime'])
    return df


def load_pypsa_hydro_dispatch(
    network_path: str | Path,
    snapshots: Optional[pd.DatetimeIndex] = None,
) -> pd.DataFrame:
    """Load PyPSA network and extract hydro dispatch.
    
    Parameters
    ----------
    network_path : str | Path
        Path to PyPSA network file
    snapshots : pd.DatetimeIndex, optional
        Specific snapshots to extract (default: all)
        
    Returns
    -------
    pd.DataFrame
        DataFrame with columns: DateTime, name, value (MW)
    """
    network = pypsa.Network(network_path)
    
    # Optimize if not already optimized
    if network.objective is None:
        if snapshots is not None:
            network.optimize(snapshots=snapshots, solver_name='gurobi')
        else:
            network.optimize(solver_name='gurobi')
    
    # Get hydro generators
    hydro_gens = network.generators[network.generators['carrier'] == 'hydro']
    hydro_gens_active = hydro_gens[hydro_gens['p_nom'] > 0]
    
    # Extract dispatch
    if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
        dispatch_data = []
        for gen_name in hydro_gens_active.index:
            gen_dispatch = network.generators_t.p[gen_name]
            if snapshots is not None:
                gen_dispatch = gen_dispatch.loc[snapshots]
            
            for dt, value in gen_dispatch.items():
                dispatch_data.append({
                    'DateTime': dt,
                    'name': gen_name,
                    'value': value
                })
        
        df = pd.DataFrame(dispatch_data)
        if not df.empty:
            df['DateTime'] = pd.to_datetime(df['DateTime'])
        return df
    else:
        return pd.DataFrame(columns=['DateTime', 'name', 'value'])


def load_sienna_hydro_dispatch(
    dispatch_file: str | Path,
) -> pd.DataFrame:
    """Load Sienna per-generator hydro dispatch.
    
    Parameters
    ----------
    dispatch_file : str | Path
        Path to sienna_hydro_per_generator.csv
        
    Returns
    -------
    pd.DataFrame
        DataFrame with columns: DateTime, name, value (MW)
    """
    df = pd.read_csv(dispatch_file, parse_dates=['DateTime'])
    return df


def compare_hydro_dispatch(
    pypsa_network_path: str | Path = None,
    pypsa_dispatch_file: str | Path = None,
    sienna_dispatch_file: str | Path = None,
    output_dir: str | Path = "tests/test_output",
    snapshots: Optional[pd.DatetimeIndex] = None,
):
    """Compare PyPSA and Sienna hydro dispatch.
    
    Parameters
    ----------
    pypsa_network_path : str | Path, optional
        Path to PyPSA network file (only used if pypsa_dispatch_file is not provided)
    pypsa_dispatch_file : str | Path, optional
        Path to saved pypsa_hydro_per_generator.csv (preferred - avoids re-optimization)
    sienna_dispatch_file : str | Path, optional
        Path to sienna_hydro_per_generator.csv
    output_dir : str | Path
        Directory to save comparison plots and tables
    snapshots : pd.DatetimeIndex, optional
        Specific snapshots to compare (default: first 168 hours)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("HYDRO DISPATCH COMPARISON: PyPSA vs Sienna")
    print("=" * 80)
    
    # Load PyPSA dispatch
    print("\n1. Loading PyPSA hydro dispatch...")
    if pypsa_dispatch_file and Path(pypsa_dispatch_file).exists():
        print(f"   Loading from saved file: {pypsa_dispatch_file}")
        pypsa_df = load_pypsa_hydro_dispatch_from_file(pypsa_dispatch_file)
    elif pypsa_network_path:
        print(f"   Optimizing PyPSA network: {pypsa_network_path}")
        print("   (Note: This will re-optimize. Use pypsa_dispatch_file to use saved results)")
        pypsa_df = load_pypsa_hydro_dispatch(pypsa_network_path, snapshots=snapshots)
    else:
        raise ValueError("Either pypsa_dispatch_file or pypsa_network_path must be provided")
    if pypsa_df.empty:
        print("   ✗ No PyPSA dispatch data found")
        return
    
    # Load Sienna dispatch
    print("2. Loading Sienna hydro dispatch...")
    if sienna_dispatch_file is None:
        sienna_dispatch_file = output_dir / "sienna_hydro_per_generator.csv"
    sienna_df = load_sienna_hydro_dispatch(sienna_dispatch_file)
    if sienna_df.empty:
        print("   ✗ No Sienna dispatch data found")
        return
    
    # Align time ranges
    pypsa_times = set(pypsa_df['DateTime'].unique())
    sienna_times = set(sienna_df['DateTime'].unique())
    common_times = sorted(pypsa_times & sienna_times)
    
    if not common_times:
        print("   ✗ No overlapping timesteps between PyPSA and Sienna")
        return
    
    print(f"   ✓ Found {len(common_times)} common timesteps")
    
    # Filter to common times
    pypsa_df = pypsa_df[pypsa_df['DateTime'].isin(common_times)].copy()
    sienna_df = sienna_df[sienna_df['DateTime'].isin(common_times)].copy()
    
    # Get common generators
    pypsa_gens = set(pypsa_df['name'].unique())
    sienna_gens = set(sienna_df['name'].unique())
    common_gens = sorted(pypsa_gens & sienna_gens)
    
    print(f"   ✓ Found {len(common_gens)} common generators")
    
    # Create comparison table
    print("\n3. Creating comparison table...")
    comparison_data = []
    
    for gen_name in common_gens:
        pypsa_gen = pypsa_df[pypsa_df['name'] == gen_name].copy()
        sienna_gen = sienna_df[sienna_df['name'] == gen_name].copy()
        
        # Calculate statistics
        pypsa_total = pypsa_gen['value'].sum()
        pypsa_max = pypsa_gen['value'].max()
        pypsa_avg = pypsa_gen['value'].mean()
        pypsa_zero = (pypsa_gen['value'] == 0).sum()
        
        sienna_total = sienna_gen['value'].sum()
        sienna_max = sienna_gen['value'].max()
        sienna_avg = sienna_gen['value'].mean()
        sienna_zero = (sienna_gen['value'] == 0).sum()
        
        # Calculate differences
        total_diff = sienna_total - pypsa_total
        total_diff_pct = (total_diff / pypsa_total * 100) if pypsa_total > 0 else 0
        max_diff = sienna_max - pypsa_max
        max_diff_pct = (max_diff / pypsa_max * 100) if pypsa_max > 0 else 0
        
        comparison_data.append({
            'name': gen_name,
            'pypsa_total_mwh': pypsa_total,
            'sienna_total_mwh': sienna_total,
            'total_diff_mwh': total_diff,
            'total_diff_pct': total_diff_pct,
            'pypsa_max_mw': pypsa_max,
            'sienna_max_mw': sienna_max,
            'max_diff_mw': max_diff,
            'max_diff_pct': max_diff_pct,
            'pypsa_avg_mw': pypsa_avg,
            'sienna_avg_mw': sienna_avg,
            'pypsa_zero_timesteps': pypsa_zero,
            'sienna_zero_timesteps': sienna_zero,
        })
    
    comparison_df = pd.DataFrame(comparison_data)
    
    # Print summary table
    print("\n" + "-" * 80)
    print("PER-GENERATOR COMPARISON")
    print("-" * 80)
    print(f"{'Generator':<25} | {'PyPSA Total':>12} | {'Sienna Total':>12} | {'Diff %':>8} | {'PyPSA Max':>10} | {'Sienna Max':>10} | {'Diff %':>8}")
    print("-" * 80)
    
    for _, row in comparison_df.iterrows():
        print(f"{row['name']:<25} | "
              f"{row['pypsa_total_mwh']:>12.2f} | "
              f"{row['sienna_total_mwh']:>12.2f} | "
              f"{row['total_diff_pct']:>7.1f}% | "
              f"{row['pypsa_max_mw']:>10.2f} | "
              f"{row['sienna_max_mw']:>10.2f} | "
              f"{row['max_diff_pct']:>7.1f}%")
    
    # Overall summary
    print("\n" + "-" * 80)
    print("OVERALL SUMMARY")
    print("-" * 80)
    pypsa_total_all = comparison_df['pypsa_total_mwh'].sum()
    sienna_total_all = comparison_df['sienna_total_mwh'].sum()
    total_diff_all = sienna_total_all - pypsa_total_all
    total_diff_pct_all = (total_diff_all / pypsa_total_all * 100) if pypsa_total_all > 0 else 0
    
    print(f"Total PyPSA Dispatch: {pypsa_total_all:.2f} MWh")
    print(f"Total Sienna Dispatch: {sienna_total_all:.2f} MWh")
    print(f"Total Difference: {total_diff_all:.2f} MWh ({total_diff_pct_all:.1f}%)")
    print(f"PyPSA Zero Timesteps: {comparison_df['pypsa_zero_timesteps'].sum()}")
    print(f"Sienna Zero Timesteps: {comparison_df['sienna_zero_timesteps'].sum()}")
    
    # Save comparison table
    comparison_file = output_dir / "hydro_dispatch_pypsa_vs_sienna.csv"
    comparison_df.to_csv(comparison_file, index=False)
    print(f"\n✓ Comparison table saved to: {comparison_file}")
    
    # Create plots
    print("\n4. Creating comparison plots...")
    
    # Plot 1: Total dispatch over time
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    
    # Aggregate by time
    pypsa_by_time = pypsa_df.groupby('DateTime')['value'].sum().sort_index()
    sienna_by_time = sienna_df.groupby('DateTime')['value'].sum().sort_index()
    
    axes[0].plot(pypsa_by_time.index, pypsa_by_time.values, label='PyPSA', linewidth=2, alpha=0.8)
    axes[0].plot(sienna_by_time.index, sienna_by_time.values, label='Sienna', linewidth=2, alpha=0.8)
    axes[0].set_xlabel('Time')
    axes[0].set_ylabel('Total Hydro Dispatch (MW)')
    axes[0].set_title('Total Hydro Dispatch Over Time')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Plot 2: Per-generator comparison (first 5 generators)
    for i, gen_name in enumerate(common_gens[:5]):
        pypsa_gen = pypsa_df[pypsa_df['name'] == gen_name].sort_values('DateTime')
        sienna_gen = sienna_df[sienna_df['name'] == gen_name].sort_values('DateTime')
        
        axes[1].plot(pypsa_gen['DateTime'], pypsa_gen['value'], 
                    label=f"PyPSA: {gen_name}", linewidth=1.5, alpha=0.7)
        axes[1].plot(sienna_gen['DateTime'], sienna_gen['value'], 
                    label=f"Sienna: {gen_name}", linewidth=1.5, alpha=0.7, linestyle='--')
    
    axes[1].set_xlabel('Time')
    axes[1].set_ylabel('Dispatch (MW)')
    axes[1].set_title('Per-Generator Dispatch Comparison (First 5 Generators)')
    axes[1].legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plot_file = output_dir / "hydro_dispatch_comparison.png"
    plt.savefig(plot_file, dpi=150, bbox_inches='tight')
    print(f"✓ Comparison plot saved to: {plot_file}")
    plt.close()
    
    # Plot 2: Scatter plot of total dispatch per generator
    fig, ax = plt.subplots(figsize=(10, 8))
    
    ax.scatter(comparison_df['pypsa_total_mwh'], comparison_df['sienna_total_mwh'], 
               s=100, alpha=0.6, edgecolors='black', linewidth=1)
    
    # Add diagonal line (perfect match)
    max_val = max(comparison_df['pypsa_total_mwh'].max(), comparison_df['sienna_total_mwh'].max())
    ax.plot([0, max_val], [0, max_val], 'r--', linewidth=2, label='Perfect Match', alpha=0.5)
    
    # Add generator labels
    for _, row in comparison_df.iterrows():
        ax.annotate(row['name'], 
                   (row['pypsa_total_mwh'], row['sienna_total_mwh']),
                   fontsize=8, alpha=0.7)
    
    ax.set_xlabel('PyPSA Total Dispatch (MWh)')
    ax.set_ylabel('Sienna Total Dispatch (MWh)')
    ax.set_title('Per-Generator Total Dispatch Comparison')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    scatter_file = output_dir / "hydro_dispatch_scatter.png"
    plt.savefig(scatter_file, dpi=150, bbox_inches='tight')
    print(f"✓ Scatter plot saved to: {scatter_file}")
    plt.close()
    
    print("\n" + "=" * 80)
    print("COMPARISON COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    # Default paths
    pypsa_network = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    pypsa_dispatch = Path("tests/test_output/pypsa_hydro_per_generator.csv")  # Preferred - saved from test
    sienna_dispatch = Path("tests/test_output/sienna_hydro_per_generator.csv")
    output_dir = Path("tests/test_output")
    
    # Allow command-line arguments
    # First arg can be either network file or dispatch file
    if len(sys.argv) > 1:
        arg1 = Path(sys.argv[1])
        if arg1.suffix == '.csv':
            pypsa_dispatch = arg1
            pypsa_network = None
        else:
            pypsa_network = arg1
            pypsa_dispatch = None  # Will use network file instead
    if len(sys.argv) > 2:
        sienna_dispatch = Path(sys.argv[2])
    if len(sys.argv) > 3:
        output_dir = Path(sys.argv[3])
    
    compare_hydro_dispatch(
        pypsa_network_path=pypsa_network,
        pypsa_dispatch_file=pypsa_dispatch,
        sienna_dispatch_file=sienna_dispatch,
        output_dir=output_dir,
    )

