#!/usr/bin/env python3
"""Plot inter-area power flows from Sienna dispatch results."""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import argparse
from loguru import logger

def load_sienna_dispatch(csv_file):
    """Load Sienna dispatch CSV and return DataFrame."""
    csv_file = Path(csv_file)
    if not csv_file.exists():
        raise FileNotFoundError(f"Sienna dispatch file not found: {csv_file}")
    
    df = pd.read_csv(csv_file)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    return df

def plot_inter_area_flows(dispatch_file, output_file=None):
    """Plot inter-area power flows over time.
    
    Args:
        dispatch_file: Path to sienna_dispatch.csv
        output_file: Optional path to save plot (default: tests/test_output/plot_inter_area_flows.png)
    """
    # Load dispatch data
    df = load_sienna_dispatch(dispatch_file)
    
    # Filter for interchange flows
    interchange_df = df[df['carrier'] == 'interchange'].copy()
    
    if interchange_df.empty:
        logger.warning("No interchange flow data found in dispatch file")
        return
    
    # Pivot to have time on x-axis and flows on y-axis
    pivot_df = interchange_df.pivot_table(
        index='DateTime',
        columns='name',
        values='value',
        aggfunc='sum'
    )
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Plot each inter-area flow
    for col in pivot_df.columns:
        ax.plot(pivot_df.index, pivot_df[col], label=col, linewidth=1.5, alpha=0.7)
    
    # Add zero line
    ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5, alpha=0.5)
    
    # Formatting
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Power Flow (MW)', fontsize=12)
    ax.set_title('Inter-Area Power Flows Over Time', fontsize=14, fontweight='bold')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # Rotate x-axis labels
    plt.xticks(rotation=45, ha='right')
    
    plt.tight_layout()
    
    # Save to test_output directory
    if output_file:
        output_path = Path(output_file)
    else:
        script_dir = Path(__file__).parent
        output_path = script_dir / "test_output" / "plot_inter_area_flows.png"
    
    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    logger.info(f"Plot saved to: {output_path}")
    
    plt.close()

def plot_inter_area_flows_heatmap(dispatch_file, output_file=None):
    """Plot inter-area flows as a heatmap (flows vs time).
    
    Args:
        dispatch_file: Path to sienna_dispatch.csv
        output_file: Optional path to save plot (default: tests/test_output/plot_inter_area_flows_heatmap.png)
    """
    # Load dispatch data
    df = load_sienna_dispatch(dispatch_file)
    
    # Filter for interchange flows
    interchange_df = df[df['carrier'] == 'interchange'].copy()
    
    if interchange_df.empty:
        logger.warning("No interchange flow data found in dispatch file")
        return
    
    # Pivot to have time on x-axis and flows on y-axis
    pivot_df = interchange_df.pivot_table(
        index='DateTime',
        columns='name',
        values='value',
        aggfunc='sum'
    )
    
    # Create heatmap
    fig, ax = plt.subplots(figsize=(14, max(8, len(pivot_df.columns) * 0.5)))
    
    # Create heatmap
    im = ax.imshow(
        pivot_df.T.values,
        aspect='auto',
        cmap='RdBu_r',
        interpolation='nearest',
        vmin=-pivot_df.abs().max().max(),
        vmax=pivot_df.abs().max().max()
    )
    
    # Set labels
    ax.set_xlabel('Time Step', fontsize=12)
    ax.set_ylabel('Inter-Area Flow', fontsize=12)
    ax.set_title('Inter-Area Power Flows Heatmap (MW)', fontsize=14, fontweight='bold')
    
    # Set y-axis labels
    ax.set_yticks(range(len(pivot_df.columns)))
    ax.set_yticklabels(pivot_df.columns)
    
    # Set x-axis labels (show every Nth time step to avoid crowding)
    num_ticks = min(10, len(pivot_df))
    step = max(1, len(pivot_df) // num_ticks)
    ax.set_xticks(range(0, len(pivot_df), step))
    ax.set_xticklabels([pivot_df.index[i].strftime('%Y-%m-%d %H:%M') for i in range(0, len(pivot_df), step)], 
                       rotation=45, ha='right')
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Power Flow (MW)', fontsize=10)
    
    plt.tight_layout()
    
    # Save to test_output directory
    if output_file:
        output_path = Path(output_file)
    else:
        script_dir = Path(__file__).parent
        output_path = script_dir / "test_output" / "plot_inter_area_flows_heatmap.png"
    
    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    logger.info(f"Heatmap saved to: {output_path}")
    
    plt.close()

def main():
    # Default dispatch file path
    script_dir = Path(__file__).parent
    default_dispatch_file = script_dir / "test_output" / "sienna_dispatch.csv"
    
    parser = argparse.ArgumentParser(description='Plot inter-area power flows from Sienna dispatch')
    parser.add_argument('dispatch_file', type=str, nargs='?', default=str(default_dispatch_file),
                        help=f'Path to sienna_dispatch.csv (default: {default_dispatch_file})')
    parser.add_argument('--output', '-o', type=str, default=None, help='Output file path')
    parser.add_argument('--heatmap', action='store_true', help='Create heatmap instead of line plot')
    
    args = parser.parse_args()
    
    if args.heatmap:
        plot_inter_area_flows_heatmap(args.dispatch_file, args.output)
    else:
        plot_inter_area_flows(args.dispatch_file, args.output)

if __name__ == '__main__':
    main()
