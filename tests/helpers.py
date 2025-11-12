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


def plot_energy_balance(network, timesteps):
    """
    Plots the energy balance timeseries for a given network and number of timesteps.

    Parameters:
    network: The network object containing the energy data.
    timesteps: The number of timesteps to plot.
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

    ax.set_title("Energy Balance Timeseries (Positive and Negative Values)")
    ax.set_ylabel("Supply (MW)")
    ax.set_xlabel("Time")
    # Combine legends from both plots
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, bbox_to_anchor=(1, 0), loc="lower left", title=None, ncol=1)
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