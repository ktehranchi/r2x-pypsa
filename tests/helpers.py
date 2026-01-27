import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

def plot_generator_marginal_costs(network):
    """
    Plots a bar chart of generator marginal costs for a given network.

    Parameters:
    network (pypsa.Network): The network object containing generator data.
    """
    # Get generator data
    gen_df = network.generators.copy()

    # Sort by marginal_cost
    gen_df_sorted = gen_df.sort_values("marginal_cost")

    # For a bar plot where the width is p_nom, we need to use plt.bar with x and width arguments
    # We'll use the cumulative sum of p_nom to set the left edge of each bar
    p_nom = gen_df_sorted["p_nom"].values / 1000
    marginal_cost = gen_df_sorted["marginal_cost"].replace(0, 3).values

    # Calculate left positions for each bar
    lefts = np.concatenate([[0], np.cumsum(p_nom)[:-1]])

    # Get carrier colors for each generator
    carrier_names = gen_df_sorted["carrier"].values
    carrier_colors = network.carriers["color"].reindex(carrier_names).values

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(
        x=lefts,
        height=marginal_cost,
        width=p_nom,
        align='edge',
        edgecolor='grey',  # Remove border lines
        linewidth=0.05,
        color=carrier_colors
    )

    ax.set_xlabel("Cumulative Generator p_nom (GW)", fontsize=20)
    ax.set_ylabel("Marginal Cost ($/MWh)", fontsize=20)
    ax.tick_params(axis='x', labelsize=16)
    ax.tick_params(axis='y', labelsize=16)

    # Add a legend mapping carrier colors to carrier names, positioned to the right of the plot
    unique_carriers, idx = np.unique(carrier_names, return_index=True)
    unique_colors = carrier_colors[idx]
    handles = [mpatches.Patch(color=color, label=carrier) for carrier, color in zip(unique_carriers, unique_colors)]

    ax.legend(handles=handles, title="Carrier", fontsize=14, title_fontsize=16, loc="center left", bbox_to_anchor=(1.02, 0.5))

    plt.tight_layout()
    plt.close()
    # plt.show()


def plot_energy_balance(network, timesteps, label="PyPSA"):
    """
    Plots the energy balance timeseries for a given network and number of timesteps.

    Parameters:
    network: The network object containing the energy data.
    timesteps: The number of timesteps to plot.
    label: Label for the plot (default: "PyPSA").
    """
    # Prepare the data
    energy_balance = (
        network.statistics.energy_balance(comps=["Generator", "StorageUnit"], aggregate_time=False, nice_names=False)
        .loc[:, :]
        .droplevel(0)
        .iloc[:, :timesteps]
        .groupby("carrier")
        .sum()
        .where(lambda x: np.abs(x) > 0)
        .fillna(0)
        .T
    )

    # Separate positive and negative values
    energy_pos = energy_balance.clip(lower=0)
    energy_neg = energy_balance.clip(upper=0)

    # Get color mapping for carriers
    carrier_colors = network.carriers.color.reindex(energy_balance.columns)
    color_dict = carrier_colors.to_dict()

    # Plot both positive and negative values on the same plot, using carrier colors
    fig, ax = plt.subplots(figsize=(10, 5))
    energy_pos.plot.area(
        ax=ax,
        stacked=True,
        legend=False,
        color=[color_dict.get(c, None) for c in energy_pos.columns]
    )
    energy_neg.plot.area(
        ax=ax,
        stacked=True,
        legend=False,
        color=[color_dict.get(c, None) for c in energy_neg.columns]
    )

    # Fix y-limits to show the full range of data
    ymin = energy_neg.sum(axis=1).min()
    ymax = energy_pos.sum(axis=1).max()
    ax.set_ylim(ymin, ymax)

    ax.set_title(f"{label} Energy Balance Timeseries (Positive and Negative Values)")
    ax.set_ylabel("Supply (MW)")
    ax.set_xlabel("Time")
    # Combine legends from both plots
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, bbox_to_anchor=(1, 0), loc="lower left", title=None, ncol=1)
    plt.close()
    # plt.show()
    return fig, ax


def plot_sienna_energy_balance(dispatch_file, timesteps=None, label="Sienna"):
    """
    Plots the energy balance timeseries from Sienna dispatch results.

    Parameters:
    dispatch_file: Path to CSV file with Sienna dispatch data (columns: DateTime, carrier, value).
    timesteps: Number of timesteps to plot (default: None, plots all). Use 7*24 for 1 week.
    label: Label for the plot (default: "Sienna").
    """
    import pandas as pd
    from pathlib import Path
    
    dispatch_file = Path(dispatch_file)
    if not dispatch_file.exists():
        raise FileNotFoundError(f"Sienna dispatch file not found: {dispatch_file}")
    
    # Read dispatch data
    df = pd.read_csv(dispatch_file)
    
    # Pivot to get carriers as columns, time as index
    if 'DateTime' in df.columns:
        df['DateTime'] = pd.to_datetime(df['DateTime'])
        energy_balance = df.pivot_table(
            index='DateTime',
            columns='carrier',
            values='value',
            aggfunc='sum'
        ).fillna(0)
    else:
        # Fallback if DateTime column doesn't exist
        energy_balance = df.pivot_table(
            index=df.index,
            columns='carrier',
            values='value',
            aggfunc='sum'
        ).fillna(0)
    
    # Limit to specified number of timesteps (e.g., 7*24 = 168 for 1 week)
    if timesteps is not None:
        energy_balance = energy_balance.iloc[:timesteps]

    # Exclude 'interchange' carrier from the plot
    if 'interchange' in energy_balance.columns:
        energy_balance = energy_balance.drop(columns=['interchange'])

    # Separate positive and negative values
    energy_pos = energy_balance.clip(lower=0)
    energy_neg = energy_balance.clip(upper=0)
    
    # Plot both positive and negative values
    fig, ax = plt.subplots(figsize=(10, 5))
    energy_pos.plot.area(
        ax=ax,
        stacked=True,
        legend=True,
    )
    energy_neg.plot.area(
        ax=ax,
        stacked=True,
        legend=False,
    )
    
    # Fix y-limits to show the full range of data
    ymin = energy_neg.sum(axis=1).min()
    ymax = energy_pos.sum(axis=1).max()
    ax.set_ylim(ymin, ymax)
    
    ax.set_title(f"{label} Energy Balance Timeseries (Positive and Negative Values)")
    ax.set_ylabel("Supply (MW)")
    ax.set_xlabel("Time")
    ax.legend(bbox_to_anchor=(1, 0), loc="lower left", title="Carrier", ncol=1)
    plt.tight_layout()
    plt.close()
    # plt.show()
    return fig, ax


def plot_interchange_flows(pypsa_dispatch_file, sienna_dispatch_file=None, timesteps=None):
    """
    Plot link/interchange flows from PyPSA and optionally Sienna dispatch CSVs.

    Parameters:
    pypsa_dispatch_file: Path to PyPSA dispatch CSV (expects carrier='link' rows).
    sienna_dispatch_file: Path to Sienna dispatch CSV (expects carrier='interchange' rows). Optional.
    timesteps: Number of timesteps to plot (default: None, plots all).
    """
    from pathlib import Path

    pypsa_dispatch_file = Path(pypsa_dispatch_file)
    has_pypsa = pypsa_dispatch_file.exists()
    has_sienna = sienna_dispatch_file is not None and Path(sienna_dispatch_file).exists()

    if not has_pypsa and not has_sienna:
        return None, None

    num_panels = has_pypsa + has_sienna
    fig, axes = plt.subplots(num_panels, 1, figsize=(12, 5 * num_panels), squeeze=False)
    ax_idx = 0

    if has_pypsa:
        df = pd.read_csv(pypsa_dispatch_file)
        df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
        df = df.dropna(subset=['DateTime'])
        link_df = df[df['carrier'] == 'link']
        if not link_df.empty:
            pivot = link_df.pivot_table(index='DateTime', columns='name', values='value', aggfunc='sum').fillna(0)
            if timesteps is not None:
                pivot = pivot.iloc[:timesteps]
            pivot.plot(ax=axes[ax_idx, 0], linewidth=1)
            axes[ax_idx, 0].set_title("PyPSA Link Flows (p0)")
            axes[ax_idx, 0].set_ylabel("Power (MW)")
            axes[ax_idx, 0].set_xlabel("Time")
            axes[ax_idx, 0].legend(bbox_to_anchor=(1, 0), loc="lower left", fontsize=8, ncol=1)
            axes[ax_idx, 0].axhline(y=0, color='black', linewidth=0.5, linestyle='--')
        else:
            axes[ax_idx, 0].set_title("PyPSA Link Flows (no link data found)")
        ax_idx += 1

    if has_sienna:
        df = pd.read_csv(Path(sienna_dispatch_file))
        df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
        df = df.dropna(subset=['DateTime'])
        interchange_df = df[df['carrier'] == 'interchange']
        if not interchange_df.empty:
            pivot = interchange_df.pivot_table(index='DateTime', columns='name', values='value', aggfunc='sum').fillna(0)
            if timesteps is not None:
                pivot = pivot.iloc[:timesteps]
            pivot.plot(ax=axes[ax_idx, 0], linewidth=1)
            axes[ax_idx, 0].set_title("Sienna AreaInterchange Flows")
            axes[ax_idx, 0].set_ylabel("Power (MW)")
            axes[ax_idx, 0].set_xlabel("Time")
            axes[ax_idx, 0].legend(bbox_to_anchor=(1, 0), loc="lower left", fontsize=8, ncol=1)
            axes[ax_idx, 0].axhline(y=0, color='black', linewidth=0.5, linestyle='--')
        else:
            axes[ax_idx, 0].set_title("Sienna AreaInterchange Flows (no interchange data found)")

    plt.tight_layout()
    plt.close()
    return fig, axes


def plot_capacity_comparison(network):
    """
    Plots a comparison of Optimal and Installed Capacity for the year 2030 for a given network.

    Parameters:
    network: The network object containing the capacity data.
    """
    # Extract the 'Optimal Capacity' and 'Installed Capacity' for the year 2030
    optimal_capacity = network.statistics.optimal_capacity().droplevel(0)
    installed_capacity = network.statistics.installed_capacity().droplevel(0)

    # Create a DataFrame for plotting
    capacity_comparison = pd.DataFrame({
        'Optimal Capacity': optimal_capacity.squeeze(),
        'Installed Capacity': installed_capacity.squeeze()
    }, index=optimal_capacity.index)

    # Plot the bar chart
    fig, ax = plt.subplots(figsize=(12, 6))
    capacity_comparison.plot.bar(ax=ax, color=['skyblue', 'orange'])

    # Set plot labels and title
    ax.set_ylabel('Capacity (MW)')
    ax.set_title('Comparison of Optimal and Installed Capacity for 2030')
    ax.set_xlabel('Generator Type')

    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45, ha='right')

    # Show the plot
    plt.tight_layout()
    plt.close()
    # plt.show()


def validate_load_conversion(pypsa_network, sienna_json_path, num_timesteps=10):
    """
    Validates that load time series are correctly converted from PyPSA to Sienna.

    This function compares load values between PyPSA and the Sienna JSON export to verify
    that the per-unit conversion is done correctly.

    Parameters:
    -----------
    pypsa_network : pypsa.Network
        The original PyPSA network with load data
    sienna_json_path : str or Path
        Path to the Sienna system JSON file
    num_timesteps : int
        Number of timesteps to compare (default: 10)

    Returns:
    --------
    dict with validation results including:
        - 'pypsa_total_load': Total load from PyPSA at each timestep
        - 'sienna_total_load': Reconstructed total load from Sienna at each timestep
        - 'max_error_pct': Maximum percentage error
        - 'is_valid': True if loads match within 0.1% tolerance
    """
    import json
    from pathlib import Path

    sienna_json_path = Path(sienna_json_path)

    # Step 1: Get PyPSA load values
    print("=" * 60)
    print("LOAD CONVERSION VALIDATION")
    print("=" * 60)

    # Get actual load values in MW from PyPSA
    if hasattr(pypsa_network, 'loads_t') and 'p_set' in pypsa_network.loads_t:
        pypsa_loads = pypsa_network.loads_t.p_set
    else:
        print("WARNING: No time-varying loads in PyPSA network")
        pypsa_loads = pypsa_network.loads[['p_set']].T

    # Total load per timestep
    pypsa_total = pypsa_loads.sum(axis=1).iloc[:num_timesteps]
    print(f"\nPyPSA Total Load (first {num_timesteps} timesteps):")
    print(pypsa_total.head())

    # Step 2: Load Sienna JSON and extract load info
    with open(sienna_json_path) as f:
        sienna_data = json.load(f)

    # Find loads in Sienna system
    sienna_loads = []
    for component in sienna_data.get('data', {}).get('components', []):
        if component.get('__metadata__', {}).get('type') == 'PowerLoad':
            sienna_loads.append(component)

    print(f"\nFound {len(sienna_loads)} PowerLoad components in Sienna system")

    # Step 3: Get time series data from Sienna
    time_series_dir = sienna_json_path.parent / "time_series"

    sienna_total_load = pd.Series(0.0, index=range(num_timesteps))

    for load_info in sienna_loads:
        load_name = load_info.get('name', 'unknown')
        base_power = load_info.get('base_power', 100.0)
        max_active_power_pu = load_info.get('max_active_power', 0.0)
        max_active_power_mw = max_active_power_pu * base_power

        # Get load UUID for time series lookup
        load_uuid = load_info.get('internal', {}).get('uuid', {}).get('value', '')

        # Find time series file for this load
        ts_file = time_series_dir / f"{load_uuid}__max_active_power__SingleTimeSeries.csv"

        if ts_file.exists():
            ts_df = pd.read_csv(ts_file)
            ts_values = ts_df.iloc[:num_timesteps, 1].values  # Second column is values

            # Convert from per-unit to MW
            # ts_values are in range 0-1, representing fraction of max_active_power
            actual_load_mw = ts_values * max_active_power_mw

            sienna_total_load += actual_load_mw

            print(f"\n  Load: {load_name}")
            print(f"    max_active_power (p.u.): {max_active_power_pu:.4f}")
            print(f"    max_active_power (MW): {max_active_power_mw:.2f}")
            print(f"    Time series range: [{ts_values.min():.4f}, {ts_values.max():.4f}]")
            print(f"    Actual load range: [{actual_load_mw.min():.2f}, {actual_load_mw.max():.2f}] MW")

    # Step 4: Compare
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)

    comparison = pd.DataFrame({
        'PyPSA (MW)': pypsa_total.values,
        'Sienna (MW)': sienna_total_load.values,
        'Difference': pypsa_total.values - sienna_total_load.values,
        'Error (%)': (pypsa_total.values - sienna_total_load.values) / pypsa_total.values * 100
    })
    print(comparison)

    max_error_pct = abs(comparison['Error (%)']).max()
    is_valid = max_error_pct < 0.1  # 0.1% tolerance

    print(f"\nMax Error: {max_error_pct:.4f}%")
    print(f"Validation: {'PASS' if is_valid else 'FAIL'}")

    # Step 5: Show what SiennaPRASInterface would incorrectly compute
    print("\n" + "=" * 60)
    print("SIENNA-PRAS INTERFACE ISSUE")
    print("=" * 60)
    print("If SiennaPRASInterface floors raw time series values without scaling:")
    print(f"  Raw time series values: [0.594, 0.515, 0.399, ...] (per-unit)")
    print(f"  floor(0.594) = 0, floor(0.515) = 0, etc.")
    print(f"  Result: All zeros!")
    print(f"\nCorrect computation:")
    print(f"  ts_value * max_active_power = actual_load_mw")
    print(f"  0.594 * {max_active_power_mw:.2f} = {0.594 * max_active_power_mw:.2f} MW")

    return {
        'pypsa_total_load': pypsa_total,
        'sienna_total_load': sienna_total_load,
        'max_error_pct': max_error_pct,
        'is_valid': is_valid,
        'comparison': comparison
    }


def plot_solar_dispatch_comparison(
    pypsa_dispatch_file,
    sienna_dispatch_file,
    output_dir=None,
    hours=24,
    top_n=20,
    pypsa_carrier='solar',
    sienna_carrier='PVe',
):
    """Plot per-generator solar dispatch for PyPSA vs Sienna over the first N hours.

    Produces two plots:
    1. A grid of subplots for the ``top_n`` generators with the largest total
       absolute difference, each showing PyPSA and Sienna dispatch over time.
    2. A bar chart ranking all solar generators by total absolute difference.

    Parameters
    ----------
    pypsa_dispatch_file : str or Path
        Path to the PyPSA dispatch CSV (columns: DateTime, name, carrier, value).
    sienna_dispatch_file : str or Path
        Path to the Sienna dispatch CSV (same schema).
    output_dir : str or Path, optional
        Directory for saving plots.  Defaults to the parent of *pypsa_dispatch_file*.
    hours : int
        Number of hours to plot (default 24).
    top_n : int
        Number of worst-matching generators to show in the grid plot (default 20).
    pypsa_carrier : str
        Carrier string used for solar in the PyPSA CSV (default ``'solar'``).
    sienna_carrier : str
        Carrier string used for solar in the Sienna CSV (default ``'PVe'``).
    """
    from pathlib import Path

    pypsa_dispatch_file = Path(pypsa_dispatch_file)
    sienna_dispatch_file = Path(sienna_dispatch_file)
    if output_dir is None:
        output_dir = pypsa_dispatch_file.parent
    output_dir = Path(output_dir)

    # --- Load data -----------------------------------------------------------
    pypsa_df = pd.read_csv(pypsa_dispatch_file)
    pypsa_df['DateTime'] = pd.to_datetime(pypsa_df['DateTime'])

    sienna_df = pd.read_csv(sienna_dispatch_file)
    sienna_df['DateTime'] = pd.to_datetime(sienna_df['DateTime'])

    # Filter to solar
    pypsa_solar = pypsa_df[pypsa_df['carrier'] == pypsa_carrier].copy()
    sienna_solar = sienna_df[sienna_df['carrier'] == sienna_carrier].copy()

    if pypsa_solar.empty or sienna_solar.empty:
        print(f"No solar dispatch data found (PyPSA carrier='{pypsa_carrier}', "
              f"Sienna carrier='{sienna_carrier}')")
        return

    # Restrict to first N hours
    pypsa_start = pypsa_solar['DateTime'].min()
    sienna_start = sienna_solar['DateTime'].min()
    pypsa_solar = pypsa_solar[pypsa_solar['DateTime'] < pypsa_start + pd.Timedelta(hours=hours)]
    sienna_solar = sienna_solar[sienna_solar['DateTime'] < sienna_start + pd.Timedelta(hours=hours)]

    # Pivot to wide format: rows = DateTime, columns = generator name
    pypsa_pivot = pypsa_solar.pivot_table(index='DateTime', columns='name', values='value', aggfunc='sum')
    sienna_pivot = sienna_solar.pivot_table(index='DateTime', columns='name', values='value', aggfunc='sum')

    # Align columns (generators present in both)
    common_gens = sorted(set(pypsa_pivot.columns) & set(sienna_pivot.columns))
    pypsa_only = sorted(set(pypsa_pivot.columns) - set(sienna_pivot.columns))
    sienna_only = sorted(set(sienna_pivot.columns) - set(pypsa_pivot.columns))

    if pypsa_only:
        print(f"Generators only in PyPSA ({len(pypsa_only)}): {pypsa_only[:5]}...")
    if sienna_only:
        print(f"Generators only in Sienna ({len(sienna_only)}): {sienna_only[:5]}...")

    if not common_gens:
        print("No common solar generators between PyPSA and Sienna dispatch files.")
        return

    # Align by position (both have `hours` rows; ignore timestamp format diffs)
    pypsa_vals = pypsa_pivot[common_gens].values  # shape (T, G)
    sienna_vals = sienna_pivot[common_gens].values
    min_T = min(pypsa_vals.shape[0], sienna_vals.shape[0])
    pypsa_vals = pypsa_vals[:min_T]
    sienna_vals = sienna_vals[:min_T]
    time_index = np.arange(min_T)

    # Compute per-generator total absolute difference
    abs_diff = np.abs(pypsa_vals - sienna_vals)  # (T, G)
    total_abs_diff = abs_diff.sum(axis=0)  # (G,)

    # Rank generators
    ranked_indices = np.argsort(total_abs_diff)[::-1]  # descending
    ranked_gens = [common_gens[i] for i in ranked_indices]
    ranked_diffs = total_abs_diff[ranked_indices]

    # --- Plot 1: Bar chart of all generators by total abs diff ----------------
    fig_bar, ax_bar = plt.subplots(figsize=(18, 6))
    n_show = min(50, len(ranked_gens))
    ax_bar.bar(range(n_show), ranked_diffs[:n_show], color='coral', edgecolor='darkred', linewidth=0.3)
    ax_bar.set_xticks(range(n_show))
    ax_bar.set_xticklabels([ranked_gens[i] for i in range(n_show)], rotation=90, fontsize=6)
    ax_bar.set_ylabel('Total Absolute Dispatch Difference (MWh)')
    ax_bar.set_title(f'Solar Generators Ranked by Dispatch Difference (first {hours}h)')
    ax_bar.axhline(0, color='black', linewidth=0.5)
    fig_bar.tight_layout()
    bar_path = output_dir / 'solar_dispatch_diff_ranking.png'
    fig_bar.savefig(bar_path, dpi=150)
    plt.close(fig_bar)
    print(f"Saved ranking plot to {bar_path}")

    # --- Plot 2: Grid of top_n worst generators ------------------------------
    actual_n = min(top_n, len(ranked_gens))
    ncols = 4
    nrows = (actual_n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 3.5 * nrows), sharex=True)
    axes_flat = np.array(axes).flatten() if actual_n > 1 else [axes]

    for idx in range(actual_n):
        ax = axes_flat[idx]
        gen_name = ranked_gens[idx]
        gen_col_idx = common_gens.index(gen_name)
        p_vals = pypsa_vals[:, gen_col_idx]
        s_vals = sienna_vals[:, gen_col_idx]

        ax.plot(time_index, p_vals, label='PyPSA', color='tab:blue', linewidth=1.2)
        ax.plot(time_index, s_vals, label='Sienna', color='tab:orange', linewidth=1.2, linestyle='--')
        ax.fill_between(time_index, p_vals, s_vals, alpha=0.15, color='red')

        diff_mwh = ranked_diffs[idx]
        ax.set_title(f'{gen_name}\n(diff={diff_mwh:.1f} MWh)', fontsize=8)
        ax.set_ylabel('MW', fontsize=7)
        ax.tick_params(labelsize=6)
        if idx == 0:
            ax.legend(fontsize=7)

    # Turn off unused subplots
    for idx in range(actual_n, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle(f'Top {actual_n} Solar Generators with Largest Dispatch Difference (first {hours}h)',
                 fontsize=12, y=1.01)
    fig.tight_layout()
    grid_path = output_dir / 'solar_dispatch_per_generator.png'
    fig.savefig(grid_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved per-generator plot to {grid_path}")

    # --- Plot 3: Total solar dispatch comparison -----------------------------
    pypsa_total = pypsa_vals.sum(axis=1)
    sienna_total = sienna_vals.sum(axis=1)

    fig_tot, ax_tot = plt.subplots(figsize=(12, 5))
    ax_tot.plot(time_index, pypsa_total, label='PyPSA Total Solar', color='tab:blue', linewidth=1.5)
    ax_tot.plot(time_index, sienna_total, label='Sienna Total Solar', color='tab:orange', linewidth=1.5, linestyle='--')
    ax_tot.fill_between(time_index, pypsa_total, sienna_total, alpha=0.15, color='red')
    ax_tot.set_xlabel('Hour')
    ax_tot.set_ylabel('MW')
    ax_tot.set_title(f'Total Solar Dispatch Comparison (first {hours}h)')
    ax_tot.legend()
    total_diff = np.abs(pypsa_total - sienna_total).sum()
    ax_tot.annotate(f'Total abs diff: {total_diff:,.1f} MWh', xy=(0.02, 0.95),
                    xycoords='axes fraction', fontsize=10, va='top',
                    bbox=dict(boxstyle='round', fc='lightyellow'))
    fig_tot.tight_layout()
    total_path = output_dir / 'solar_dispatch_total_comparison.png'
    fig_tot.savefig(total_path, dpi=150)
    plt.close(fig_tot)
    print(f"Saved total solar comparison to {total_path}")

    # --- Print summary -------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"SOLAR DISPATCH COMPARISON SUMMARY (first {hours}h)")
    print(f"{'='*70}")
    print(f"Common generators: {len(common_gens)}")
    print(f"Total abs difference (all gens): {total_diff:,.1f} MWh")
    print(f"\nTop {min(10, actual_n)} generators by dispatch difference:")
    for i in range(min(10, actual_n)):
        gen_col_idx = common_gens.index(ranked_gens[i])
        p_sum = pypsa_vals[:, gen_col_idx].sum()
        s_sum = sienna_vals[:, gen_col_idx].sum()
        print(f"  {i+1:2d}. {ranked_gens[i]:40s}  diff={ranked_diffs[i]:10.1f} MWh  "
              f"(PyPSA={p_sum:10.1f}, Sienna={s_sum:10.1f})")
    print(f"{'='*70}")