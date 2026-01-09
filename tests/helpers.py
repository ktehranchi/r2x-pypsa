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
    plt.show()


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
    plt.show()
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
    plt.show()
    return fig, ax


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
    plt.show()


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