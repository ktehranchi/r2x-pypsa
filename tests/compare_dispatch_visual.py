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

# Add parent directory to path to import helpers
sys.path.insert(0, str(Path(__file__).parent))
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
        'other': '#808080',
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


def plot_side_by_side_energy_balance(pypsa_df, sienna_df, carrier_colors, timesteps=168, output_file=None):
    """Create side-by-side energy balance plots.
    
    Parameters:
        pypsa_df: DataFrame with columns DateTime, carrier, value
        sienna_df: DataFrame with columns DateTime, carrier, value
        carrier_colors: dict mapping carrier names to colors
        timesteps: Number of timesteps to plot (default: 168 for 1 week)
        output_file: Optional path to save the plot
    """
    # Map Sienna carrier names to PyPSA carrier names for consistency
    sienna_df_mapped = sienna_df.copy()
    sienna_df_mapped['carrier'] = sienna_df_mapped['carrier'].apply(map_sienna_to_pypsa_carrier)
    
    # Pivot to get carriers as columns, time as index
    pypsa_balance = pypsa_df.pivot_table(
        index='DateTime',
        columns='carrier',
        values='value',
        aggfunc='sum'
    ).fillna(0)
    
    sienna_balance = sienna_df_mapped.pivot_table(
        index='DateTime',
        columns='carrier',
        values='value',
        aggfunc='sum'
    ).fillna(0)
    
    # Limit to specified timesteps
    if timesteps is not None:
        pypsa_balance = pypsa_balance.iloc[:timesteps]
        sienna_balance = sienna_balance.iloc[:timesteps]
    
    # Separate positive and negative values
    pypsa_pos = pypsa_balance.clip(lower=0)
    pypsa_neg = pypsa_balance.clip(upper=0)
    sienna_pos = sienna_balance.clip(lower=0)
    sienna_neg = sienna_balance.clip(upper=0)
    
    # Get all unique carriers from both datasets
    all_carriers = sorted(set(pypsa_balance.columns) | set(sienna_balance.columns))
    
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
    
    # Get colors for carriers (use PyPSA colors, fallback to default if missing)
    pypsa_colors = [carrier_colors.get(c, '#808080') for c in all_carriers]
    sienna_colors = [carrier_colors.get(c, '#808080') for c in all_carriers]
    
    # Calculate y-axis limits (same for both plots)
    ymin = min(pypsa_neg.sum(axis=1).min(), sienna_neg.sum(axis=1).min())
    ymax = max(pypsa_pos.sum(axis=1).max(), sienna_pos.sum(axis=1).max())
    
    # Create side-by-side plots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 6))
    
    # PyPSA plot (left)
    pypsa_pos.plot.area(
        ax=ax1,
        stacked=True,
        legend=False,
        color=pypsa_colors
    )
    pypsa_neg.plot.area(
        ax=ax1,
        stacked=True,
        legend=False,
        color=pypsa_colors
    )
    ax1.set_ylim(ymin, ymax)
    ax1.set_title("PyPSA Energy Balance", fontsize=14, fontweight='bold')
    ax1.set_ylabel("Supply (MW)", fontsize=12)
    ax1.set_xlabel("Time", fontsize=12)
    ax1.grid(True, alpha=0.3)
    
    # Sienna plot (right)
    sienna_pos.plot.area(
        ax=ax2,
        stacked=True,
        legend=False,
        color=sienna_colors
    )
    sienna_neg.plot.area(
        ax=ax2,
        stacked=True,
        legend=False,
        color=sienna_colors
    )
    ax2.set_ylim(ymin, ymax)
    ax2.set_title("Sienna Energy Balance", fontsize=14, fontweight='bold')
    ax2.set_ylabel("Supply (MW)", fontsize=12)
    ax2.set_xlabel("Time", fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    # Create shared legend
    import matplotlib.patches as mpatches
    handles = [mpatches.Patch(color=carrier_colors.get(c, '#808080'), label=c) for c in all_carriers]
    fig.legend(handles, all_carriers, bbox_to_anchor=(0.5, -0.05), loc='lower center', ncol=min(len(all_carriers), 8))
    
    plt.tight_layout()
    
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
        default='tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc',
        help='Path to PyPSA network file (for carrier colors)'
    )
    parser.add_argument(
        '--sienna-json',
        type=str,
        default='tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json',
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
    if not args.no_show:
        plt.show()
    else:
        plt.close()
    
    # Create marginal costs plot
    logger.info("Creating marginal costs comparison plot...")
    marginal_costs_file = output_dir / "dispatch_comparison_marginal_costs.png"
    plot_marginal_costs_comparison(
        args.network_file,
        args.sienna_json,
        carrier_colors,
        output_file=str(marginal_costs_file)
    )
    if not args.no_show:
        plt.show()
    else:
        plt.close()
    
    logger.info("Comparison complete!")


if __name__ == "__main__":
    main()

