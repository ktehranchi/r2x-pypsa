"""Plot total renewable dispatch for PyPSA and Sienna on the same graph."""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from loguru import logger
import pypsa

def plot_renewable_totals():
    """Plot sum of renewables for both PyPSA and Sienna."""
    
    # Paths
    pypsa_dispatch_file = Path("tests/test_output/pypsa_dispatch.csv")
    sienna_dispatch_file = Path("tests/test_output/sienna_dispatch.csv")
    output_file = Path("tests/test_output/renewable_totals_comparison.png")
    
    logger.info("Loading dispatch data...")
    
    # Load PyPSA dispatch
    pypsa_df = pd.read_csv(pypsa_dispatch_file)
    pypsa_df['DateTime'] = pd.to_datetime(pypsa_df['DateTime'])
    
    # Load Sienna dispatch
    sienna_df = pd.read_csv(sienna_dispatch_file)
    sienna_df['DateTime'] = pd.to_datetime(sienna_df['DateTime'])
    
    # Define renewable carriers
    pypsa_renewable_carriers = ['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'hydro', 'ror']
    sienna_renewable_carriers = ['PVe', 'WT', 'HY']  # Solar, Wind, Hydro
    
    # Filter for renewables
    pypsa_renewables = pypsa_df[pypsa_df['carrier'].isin(pypsa_renewable_carriers)].copy()
    sienna_renewables = sienna_df[sienna_df['carrier'].isin(sienna_renewable_carriers)].copy()
    
    # Sum renewables by timestamp
    pypsa_totals = pypsa_renewables.groupby('DateTime')['value'].sum().reset_index()
    pypsa_totals.columns = ['DateTime', 'PyPSA_Renewables_MW']
    pypsa_totals = pypsa_totals.sort_values('DateTime')
    
    sienna_totals = sienna_renewables.groupby('DateTime')['value'].sum().reset_index()
    sienna_totals.columns = ['DateTime', 'Sienna_Renewables_MW']
    sienna_totals = sienna_totals.sort_values('DateTime')
    
    # Get load data
    pypsa_load = pypsa_df[pypsa_df['carrier'] == 'load'].copy()
    sienna_load = sienna_df[sienna_df['carrier'] == 'load'].copy()
    
    # Sum load by timestamp and multiply by 100 to convert to MW
    pypsa_load_totals = pypsa_load.groupby('DateTime')['value'].sum().reset_index()
    pypsa_load_totals['value'] = pypsa_load_totals['value'] * 100  # Convert to MW
    pypsa_load_totals.columns = ['DateTime', 'PyPSA_Load_MW']
    pypsa_load_totals = pypsa_load_totals.sort_values('DateTime')
    
    sienna_load_totals = sienna_load.groupby('DateTime')['value'].sum().reset_index()
    sienna_load_totals['value'] = sienna_load_totals['value'] * 100  # Convert to MW
    sienna_load_totals.columns = ['DateTime', 'Sienna_Load_MW']
    sienna_load_totals = sienna_load_totals.sort_values('DateTime')
    
    # Filter to first 4 days (hours 0-95, since 4 days * 24 hours = 96 hours, so 0-95 inclusive)
    start_datetime = pypsa_totals['DateTime'].min()
    first_4_days_start = start_datetime
    first_4_days_end = start_datetime + pd.Timedelta(hours=95)  # 4 days = 96 hours (0-95)
    pypsa_totals = pypsa_totals[(pypsa_totals['DateTime'] >= first_4_days_start) & (pypsa_totals['DateTime'] <= first_4_days_end)].copy()
    sienna_totals = sienna_totals[(sienna_totals['DateTime'] >= first_4_days_start) & (sienna_totals['DateTime'] <= first_4_days_end)].copy()
    pypsa_load_totals = pypsa_load_totals[(pypsa_load_totals['DateTime'] >= first_4_days_start) & (pypsa_load_totals['DateTime'] <= first_4_days_end)].copy()
    sienna_load_totals = sienna_load_totals[(sienna_load_totals['DateTime'] >= first_4_days_start) & (sienna_load_totals['DateTime'] <= first_4_days_end)].copy()
    
    logger.info(f"PyPSA renewable data points: {len(pypsa_totals)}")
    logger.info(f"Sienna renewable data points: {len(sienna_totals)}")
    logger.info(f"PyPSA total renewable energy: {pypsa_totals['PyPSA_Renewables_MW'].sum():.2f} MWh")
    logger.info(f"Sienna total renewable energy: {sienna_totals['Sienna_Renewables_MW'].sum():.2f} MWh")
    
    # Calculate y-axis limits to properly scale the plot
    all_values = pd.concat([
        pypsa_totals['PyPSA_Renewables_MW'],
        sienna_totals['Sienna_Renewables_MW'],
        pypsa_load_totals['PyPSA_Load_MW'],
        sienna_load_totals['Sienna_Load_MW']
    ])
    y_min = all_values.min()
    y_max = all_values.max()
    y_range = y_max - y_min
    # Add 5% padding on top and bottom
    y_padding = y_range * 0.05
    y_lim_min = max(0, y_min - y_padding)  # Don't go below 0
    y_lim_max = y_max + y_padding
    
    logger.info(f"Y-axis range: {y_lim_min:.2f} to {y_lim_max:.2f} MW")
    
    # Create plot
    plt.figure(figsize=(14, 8))
    
    # Plot renewables
    plt.plot(pypsa_totals['DateTime'], pypsa_totals['PyPSA_Renewables_MW'], 
             label='PyPSA Renewables', linewidth=2, alpha=0.8)
    plt.plot(sienna_totals['DateTime'], sienna_totals['Sienna_Renewables_MW'], 
             label='Sienna Renewables', linewidth=2, alpha=0.8)
    
    # Plot load
    plt.plot(pypsa_load_totals['DateTime'], pypsa_load_totals['PyPSA_Load_MW'], 
             label='PyPSA Load', linewidth=2, alpha=0.8, linestyle='--')
    plt.plot(sienna_load_totals['DateTime'], sienna_load_totals['Sienna_Load_MW'], 
             label='Sienna Load', linewidth=2, alpha=0.8, linestyle='--')
    
    # Set y-axis limits
    plt.ylim(y_lim_min, y_lim_max)
    
    plt.xlabel('DateTime', fontsize=12)
    plt.ylabel('Power (MW)', fontsize=12)
    plt.title('Renewable Dispatch and Load: PyPSA vs Sienna (First 4 Days)', fontsize=14, fontweight='bold')
    plt.legend(fontsize=11, loc='best')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save plot
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    logger.info(f"Plot saved to: {output_file}")
    
    # Print summary statistics
    logger.info("\nSummary Statistics:")
    logger.info(f"PyPSA - Mean: {pypsa_totals['PyPSA_Renewables_MW'].mean():.2f} MW, "
                f"Max: {pypsa_totals['PyPSA_Renewables_MW'].max():.2f} MW, "
                f"Min: {pypsa_totals['PyPSA_Renewables_MW'].min():.2f} MW")
    logger.info(f"Sienna - Mean: {sienna_totals['Sienna_Renewables_MW'].mean():.2f} MW, "
                f"Max: {sienna_totals['Sienna_Renewables_MW'].max():.2f} MW, "
                f"Min: {sienna_totals['Sienna_Renewables_MW'].min():.2f} MW")
    
    # Calculate difference
    if len(pypsa_totals) == len(sienna_totals):
        diff = pypsa_totals['PyPSA_Renewables_MW'].values - sienna_totals['Sienna_Renewables_MW'].values
        logger.info(f"\nDifference (PyPSA - Sienna):")
        logger.info(f"  Mean: {diff.mean():.2f} MW")
        logger.info(f"  Max: {diff.max():.2f} MW")
        logger.info(f"  Min: {diff.min():.2f} MW")
        logger.info(f"  Total energy difference: {diff.sum():.2f} MWh")
    
    # Print nuclear time series for first day
    print_nuclear_time_series(pypsa_df, sienna_df, first_4_days_start)
    
    # Check total generation vs load for first 4 days
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    check_total_generation_vs_load(pypsa_df, sienna_df, first_4_days_start, first_4_days_end, test_file)


def print_nuclear_time_series(pypsa_df, sienna_df, start_datetime):
    """Print nuclear generator time series for the first day, side by side."""
    
    logger.info("\n" + "=" * 100)
    logger.info("NUCLEAR GENERATOR TIME SERIES - FIRST DAY (24 HOURS)")
    logger.info("=" * 100)
    
    # Filter to first day (24 hours)
    first_day_end = start_datetime + pd.Timedelta(hours=23)
    pypsa_day1 = pypsa_df[(pypsa_df['DateTime'] >= start_datetime) & 
                          (pypsa_df['DateTime'] <= first_day_end)].copy()
    sienna_day1 = sienna_df[(sienna_df['DateTime'] >= start_datetime) & 
                            (sienna_df['DateTime'] <= first_day_end)].copy()
    
    # Filter for nuclear generators
    # PyPSA uses 'nuclear' as carrier
    pypsa_nuclear = pypsa_day1[pypsa_day1['carrier'] == 'nuclear'].copy()
    # Sienna uses 'ST' (Steam Turbine) with 'NUCLEAR' fuel, but carrier might be different
    # Check what carrier Sienna uses for nuclear
    sienna_nuclear_carriers = ['ST', 'nuclear', 'Nuclear', 'NUCLEAR']
    sienna_nuclear = sienna_day1[sienna_day1['carrier'].isin(sienna_nuclear_carriers)].copy()
    
    if len(pypsa_nuclear) == 0:
        logger.warning("No PyPSA nuclear generators found in dispatch data")
        return
    
    if len(sienna_nuclear) == 0:
        logger.warning("No Sienna nuclear generators found in dispatch data")
        # Try to find by name pattern
        nuclear_names = pypsa_nuclear['name'].unique()
        logger.info(f"PyPSA nuclear generator names: {list(nuclear_names)}")
        # Check if any Sienna generators match nuclear names
        for name in nuclear_names:
            matching = sienna_day1[sienna_day1['name'].str.contains(name, case=False, na=False)]
            if len(matching) > 0:
                logger.info(f"Found Sienna generator matching '{name}': {matching['carrier'].unique()}")
                sienna_nuclear = pd.concat([sienna_nuclear, matching])
    
    # Group by generator name and sum if multiple entries per timestamp
    pypsa_nuclear_grouped = pypsa_nuclear.groupby(['DateTime', 'name'])['value'].sum().reset_index()
    sienna_nuclear_grouped = sienna_nuclear.groupby(['DateTime', 'name'])['value'].sum().reset_index()
    
    # Get all unique nuclear generator names
    pypsa_nuclear_names = sorted(pypsa_nuclear_grouped['name'].unique())
    sienna_nuclear_names = sorted(sienna_nuclear_grouped['name'].unique())
    
    logger.info(f"\nPyPSA nuclear generators: {len(pypsa_nuclear_names)}")
    for name in pypsa_nuclear_names:
        gen_data = pypsa_nuclear_grouped[pypsa_nuclear_grouped['name'] == name]
        logger.info(f"  {name}: {len(gen_data)} timesteps, capacity: {gen_data['value'].max():.2f} MW")
    
    logger.info(f"\nSienna nuclear generators: {len(sienna_nuclear_names)}")
    for name in sienna_nuclear_names:
        gen_data = sienna_nuclear_grouped[sienna_nuclear_grouped['name'] == name]
        logger.info(f"  {name}: {len(gen_data)} timesteps, capacity: {gen_data['value'].max():.2f} MW")
    
    # For each nuclear generator, print time series side by side
    # Match generators by name
    all_nuclear_names = sorted(set(pypsa_nuclear_names) | set(sienna_nuclear_names))
    
    for gen_name in all_nuclear_names:
        logger.info("\n" + "-" * 100)
        logger.info(f"NUCLEAR GENERATOR: {gen_name}")
        logger.info("-" * 100)
        
        # Get PyPSA data for this generator
        pypsa_gen = pypsa_nuclear_grouped[pypsa_nuclear_grouped['name'] == gen_name].copy()
        pypsa_gen = pypsa_gen.sort_values('DateTime')
        
        # Get Sienna data for this generator
        sienna_gen = sienna_nuclear_grouped[sienna_nuclear_grouped['name'] == gen_name].copy()
        sienna_gen = sienna_gen.sort_values('DateTime')
        
        # Create a merged DataFrame for side-by-side comparison
        comparison = pd.merge(
            pypsa_gen[['DateTime', 'value']].rename(columns={'value': 'PyPSA_MW'}),
            sienna_gen[['DateTime', 'value']].rename(columns={'value': 'Sienna_MW'}),
            on='DateTime',
            how='outer'
        )
        comparison = comparison.sort_values('DateTime')
        comparison = comparison.fillna(0.0)  # Fill missing values with 0
        
        # Calculate difference
        comparison['Difference_MW'] = comparison['PyPSA_MW'] - comparison['Sienna_MW']
        comparison['Ramp_Down_MW'] = comparison['PyPSA_MW'].diff().abs()  # Change from previous hour
        
        # Print header
        logger.info(f"{'DateTime':<20} {'PyPSA (MW)':<15} {'Sienna (MW)':<15} {'Diff (MW)':<15} {'Ramp Down (MW)':<15}")
        logger.info("-" * 100)
        
        # Print each hour
        for _, row in comparison.iterrows():
            logger.info(f"{str(row['DateTime']):<20} "
                       f"{row['PyPSA_MW']:>14.2f} "
                       f"{row['Sienna_MW']:>14.2f} "
                       f"{row['Difference_MW']:>14.2f} "
                       f"{row['Ramp_Down_MW']:>14.2f}")
        
        # Print summary
        logger.info("-" * 100)
        logger.info(f"Summary for {gen_name}:")
        logger.info(f"  PyPSA - Mean: {comparison['PyPSA_MW'].mean():.2f} MW, "
                   f"Max: {comparison['PyPSA_MW'].max():.2f} MW, "
                   f"Min: {comparison['PyPSA_MW'].min():.2f} MW")
        logger.info(f"  Sienna - Mean: {comparison['Sienna_MW'].mean():.2f} MW, "
                   f"Max: {comparison['Sienna_MW'].max():.2f} MW, "
                   f"Min: {comparison['Sienna_MW'].min():.2f} MW")
        logger.info(f"  Difference - Mean: {comparison['Difference_MW'].mean():.2f} MW, "
                   f"Max: {comparison['Difference_MW'].max():.2f} MW, "
                   f"Min: {comparison['Difference_MW'].min():.2f} MW")
        logger.info(f"  PyPSA Max Ramp Down: {comparison['Ramp_Down_MW'].max():.2f} MW/h")
        
        # Calculate ramp down periods (when power decreases)
        pypsa_ramp_down = comparison['PyPSA_MW'].diff()
        sienna_ramp_down = comparison['Sienna_MW'].diff()
        ramp_down_periods = comparison[pypsa_ramp_down < 0].copy()
        if len(ramp_down_periods) > 0:
            logger.info(f"\n  Ramp Down Periods (PyPSA decreasing):")
            for _, row in ramp_down_periods.iterrows():
                prev_idx = comparison.index[comparison.index < comparison.index[comparison['DateTime'] == row['DateTime']].tolist()[0]]
                if len(prev_idx) > 0:
                    prev_row = comparison.loc[prev_idx[-1]]
                    ramp_amount = row['PyPSA_MW'] - prev_row['PyPSA_MW']
                    logger.info(f"    {row['DateTime']}: {prev_row['PyPSA_MW']:.2f} → {row['PyPSA_MW']:.2f} MW "
                               f"(Δ={ramp_amount:.2f} MW, Sienna: {prev_row['Sienna_MW']:.2f} → {row['Sienna_MW']:.2f} MW, "
                               f"Δ={row['Sienna_MW'] - prev_row['Sienna_MW']:.2f} MW)")


def check_total_generation_vs_load(pypsa_df, sienna_df, start_datetime, end_datetime, network_file):
    """Check if PyPSA total generation exceeds total load for the specified time period."""
    
    logger.info("\n" + "=" * 80)
    logger.info("TOTAL GENERATION VS LOAD CHECK - FIRST 4 DAYS")
    logger.info("=" * 80)
    
    # Load PyPSA network to get load data
    logger.info("Loading PyPSA network to get load data...")
    network = pypsa.Network(network_file)
    
    # Apply same modifications as in test_end_to_end.py
    # Set all capital costs to zero for pure economic dispatch
    for component_type in ['Generator', 'StorageUnit', 'Store', 'Link', 'Line']:
        if component_type in network.components.keys():
            df = network.df(component_type)
            if 'capital_cost' in df.columns:
                df['capital_cost'] = 0.0
            for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
                if attr in df.columns:
                    df[attr] = False
    
    # Scale load by 0.75 (as in test)
    if hasattr(network, 'loads_t') and hasattr(network.loads_t, 'p_set'):
        network.loads_t.p_set *= 0.75
    
    # Disable storage (as in test)
    if hasattr(network, 'storage_units') and len(network.storage_units) > 0:
        network.storage_units['active'] = False
    if hasattr(network, 'stores') and len(network.stores) > 0:
        network.stores['active'] = False
    
    # Filter to first 4 days
    pypsa_day3 = pypsa_df[(pypsa_df['DateTime'] >= start_datetime) & 
                          (pypsa_df['DateTime'] <= end_datetime)].copy()
    sienna_day3 = sienna_df[(sienna_df['DateTime'] >= start_datetime) & 
                           (sienna_df['DateTime'] <= end_datetime)].copy()
    
    logger.info(f"First 4 days range: {start_datetime} to {end_datetime}")
    logger.info(f"PyPSA data points: {len(pypsa_day3)}")
    logger.info(f"Sienna data points: {len(sienna_day3)}")
    
    # Calculate PyPSA total generation (all carriers except 'load' and 'AC')
    # AC refers to load, not generation
    load_carriers = ['load', 'AC']  # AC is a type of load
    pypsa_generation = pypsa_day3[~pypsa_day3['carrier'].isin(load_carriers)].copy()
    pypsa_total_gen = pypsa_generation.groupby('DateTime')['value'].sum().reset_index()
    pypsa_total_gen.columns = ['DateTime', 'Total_Generation_MW']
    pypsa_total_gen = pypsa_total_gen.sort_values('DateTime')
    
    # Get PyPSA total load from dispatch CSV (includes both 'load' and 'AC' carriers)
    # AC is a type of load
    load_carriers = ['load', 'AC']
    pypsa_load_data = pypsa_day3[pypsa_day3['carrier'].isin(load_carriers)].copy()
    
    # Regular 'load' carrier values need to be scaled by 100, AC values are already in MW
    pypsa_load_data['value_scaled'] = pypsa_load_data.apply(
        lambda row: row['value'] * 100 if row['carrier'] == 'load' else row['value'],
        axis=1
    )
    
    pypsa_total_load = pypsa_load_data.groupby('DateTime')['value_scaled'].sum().reset_index()
    pypsa_total_load.columns = ['DateTime', 'Total_Load_MW']
    pypsa_total_load = pypsa_total_load.sort_values('DateTime')
    
    # Check for Link power consumption and losses
    # Links can:
    # 1. Consume power (positive p0 values = consuming from bus0, e.g., electrolyzers)
    # 2. Have transmission losses (efficiency < 1, e.g., HVDC links)
    # First, check if network has been optimized, if not, optimize for day 3 only
    link_consumption = None
    link_losses = None
    if hasattr(network, 'links') and len(network.links) > 0:
        # Check if network has been optimized
        if not (hasattr(network, 'links_t') and hasattr(network.links_t, 'p0')):
            logger.info("Network not optimized. Optimizing for day 3 to get Link data...")
            # Get snapshots for day 3
            all_snapshots = network.snapshots
            if isinstance(all_snapshots, pd.MultiIndex):
                datetime_snapshots = pd.to_datetime([s[1] if isinstance(s, tuple) and len(s) >= 2 else s for s in all_snapshots])
            else:
                datetime_snapshots = pd.to_datetime(all_snapshots)
            
            day3_snapshots = all_snapshots[(datetime_snapshots >= start_datetime) & (datetime_snapshots <= end_datetime)]
            
            if len(day3_snapshots) > 0:
                # Optimize only for day 3 (faster)
                network.optimize(
                    snapshots=day3_snapshots,
                    solver_name='gurobi',
                    solver_options={
                        'OptimalityTol': 1e-9,
                        'FeasibilityTol': 1e-9,
                        'IntFeasTol': 1e-9,
                    }
                )
                logger.info("Network optimized for day 3")
        
        # Now check for Link consumption
        if hasattr(network, 'links_t') and hasattr(network.links_t, 'p0'):
            # Get snapshots in day 3 range
            all_snapshots = network.snapshots
            if isinstance(all_snapshots, pd.MultiIndex):
                datetime_snapshots = pd.to_datetime([s[1] if isinstance(s, tuple) and len(s) >= 2 else s for s in all_snapshots])
            else:
                datetime_snapshots = pd.to_datetime(all_snapshots)
            
            day3_snapshots = all_snapshots[(datetime_snapshots >= start_datetime) & (datetime_snapshots <= end_datetime)]
            
            if len(day3_snapshots) > 0:
                # Get Link p0 (power at bus0, positive = consuming from bus0)
                link_p0 = network.links_t.p0.loc[day3_snapshots]
                
                # DEBUG: Check if Links are actually flowing power
                logger.info(f"\nChecking Link power flows (p0) for day 3...")
                logger.info(f"  Total Links in network: {len(network.links)}")
                logger.info(f"  Link p0 DataFrame shape: {link_p0.shape}")
                logger.info(f"  Link p0 absolute sum (all snapshots, all links): {link_p0.abs().sum().sum():.2f} MW")
                logger.info(f"  Link p0 max absolute value: {link_p0.abs().max().max():.2f} MW")
                logger.info(f"  Link p0 min absolute value: {link_p0.abs().min().min():.2f} MW")
                logger.info(f"  Links with non-zero p0 (any snapshot): {(link_p0.abs() > 0.01).any().sum()}")
                
                # Check Link carriers
                if 'carrier' in network.links.columns:
                    carrier_counts = network.links['carrier'].value_counts().to_dict()
                    logger.info(f"  Link carriers: {carrier_counts}")
                
                # If p0 is all zeros, there are no link losses
                if link_p0.abs().sum().sum() < 0.01:
                    logger.info("  → All Link p0 values are ~0, so NO link losses or consumption")
                else:
                    logger.info(f"  → Links ARE flowing power, total absolute flow: {link_p0.abs().sum().sum():.2f} MW")
                    # Show which links are flowing
                    link_flows = link_p0.abs().sum()
                    active_links = link_flows[link_flows > 0.01]
                    if len(active_links) > 0:
                        logger.info(f"  Active Links (with power flow): {len(active_links)}")
                        for link_name, flow in active_links.head(10).items():
                            carrier = network.links.loc[link_name, 'carrier'] if 'carrier' in network.links.columns else 'unknown'
                            logger.info(f"    {link_name} ({carrier}): {flow:.2f} MW total")
                
                # Sum positive p0 values (consuming power) for each snapshot
                positive_consumption = link_p0[link_p0 > 0].sum(axis=1)
                
                # Convert to DataFrame with DateTime
                if isinstance(day3_snapshots, pd.MultiIndex):
                    link_datetimes = pd.to_datetime([s[1] if isinstance(s, tuple) and len(s) >= 2 else s for s in day3_snapshots])
                else:
                    link_datetimes = pd.to_datetime(day3_snapshots)
                
                link_consumption = pd.DataFrame({
                    'DateTime': link_datetimes,
                    'Link_Consumption_MW': positive_consumption.values
                })
                link_consumption = link_consumption.sort_values('DateTime')
                
                logger.info(f"Found Link power consumption: {link_consumption['Link_Consumption_MW'].sum():.2f} MWh total")
                logger.info(f"  Mean: {link_consumption['Link_Consumption_MW'].mean():.2f} MW, "
                           f"Max: {link_consumption['Link_Consumption_MW'].max():.2f} MW, "
                           f"Min: {link_consumption['Link_Consumption_MW'].min():.2f} MW")
                
                # Check for Link transmission losses (efficiency < 1)
                # For Links: p1 = p0 * efficiency when p0 > 0
                # Losses = p0 - p1 = p0 * (1 - efficiency)
                # Get Link efficiency
                if hasattr(network, 'links') and 'efficiency' in network.links.columns:
                    # Get efficiency for each link (can be time-varying or static)
                    if hasattr(network, 'links_t') and hasattr(network.links_t, 'efficiency'):
                        link_efficiency = network.links_t.efficiency.loc[day3_snapshots]
                    else:
                        # Static efficiency
                        link_efficiency = pd.DataFrame(
                            index=day3_snapshots,
                            columns=network.links.index,
                            data=network.links['efficiency'].values
                        )
                    
                    # Calculate losses: for each link, losses = p0 * (1 - efficiency) when p0 > 0
                    # Or more generally: losses = abs(p0) * (1 - efficiency) when power flows
                    # Actually: losses = p0 - p1, where p1 = p0 * efficiency
                    # So: losses = p0 * (1 - efficiency) when p0 > 0
                    link_p0_abs = link_p0.abs()
                    link_losses_per_snapshot = (link_p0_abs * (1 - link_efficiency)).sum(axis=1)
                    
                    # Convert to DataFrame with DateTime
                    if isinstance(day3_snapshots, pd.MultiIndex):
                        link_loss_datetimes = pd.to_datetime([s[1] if isinstance(s, tuple) and len(s) >= 2 else s for s in day3_snapshots])
                    else:
                        link_loss_datetimes = pd.to_datetime(day3_snapshots)
                    
                    link_losses = pd.DataFrame({
                        'DateTime': link_loss_datetimes,
                        'Link_Losses_MW': link_losses_per_snapshot.values
                    })
                    link_losses = link_losses.sort_values('DateTime')
                    
                    logger.info(f"Found Link transmission losses: {link_losses['Link_Losses_MW'].sum():.2f} MWh total")
                    logger.info(f"  Mean: {link_losses['Link_Losses_MW'].mean():.2f} MW, "
                               f"Max: {link_losses['Link_Losses_MW'].max():.2f} MW, "
                               f"Min: {link_losses['Link_Losses_MW'].min():.2f} MW")
                
                # Add Link consumption to load
                pypsa_total_load = pd.merge(pypsa_total_load, link_consumption, on='DateTime', how='outer')
                pypsa_total_load['Link_Consumption_MW'] = pypsa_total_load['Link_Consumption_MW'].fillna(0.0)
                pypsa_total_load['Total_Load_MW'] = pypsa_total_load['Total_Load_MW'] + pypsa_total_load['Link_Consumption_MW']
                
                # Add Link losses to load
                if link_losses is not None:
                    pypsa_total_load = pd.merge(pypsa_total_load, link_losses, on='DateTime', how='outer')
                    pypsa_total_load['Link_Losses_MW'] = pypsa_total_load['Link_Losses_MW'].fillna(0.0)
                    pypsa_total_load['Total_Load_MW'] = pypsa_total_load['Total_Load_MW'] + pypsa_total_load['Link_Losses_MW']
                
                pypsa_total_load = pypsa_total_load[['DateTime', 'Total_Load_MW']].copy()
            else:
                logger.warning("No snapshots found in day 3 range for Link consumption check")
        else:
            logger.warning("Could not access links_t.p0 after optimization")
    else:
        logger.info("No Links in network")
    
    # Check for Line transmission losses
    # Line losses = difference between power sent (p0) and power received (p1)
    # In PyPSA DC power flow: p0 is power at bus0, p1 is power at bus1
    # When power flows from bus0 to bus1: p0 > 0, p1 < 0
    # Losses = p0 - (-p1) = p0 + p1 (but p1 is negative, so losses = p0 - abs(p1))
    # General formula: losses = abs(abs(p0) - abs(p1)) for each line
    line_losses = None
    if hasattr(network, 'lines') and len(network.lines) > 0:
        logger.info(f"Found {len(network.lines)} Lines in network")
        # Check if network has been optimized, if not optimize for day 3
        if not (hasattr(network, 'lines_t') and hasattr(network.lines_t, 'p0') and hasattr(network.lines_t, 'p1')):
            logger.info("Network not optimized for lines. Optimizing for day 3 to get Line data...")
            # Get snapshots for day 3
            all_snapshots = network.snapshots
            if isinstance(all_snapshots, pd.MultiIndex):
                datetime_snapshots = pd.to_datetime([s[1] if isinstance(s, tuple) and len(s) >= 2 else s for s in all_snapshots])
            else:
                datetime_snapshots = pd.to_datetime(all_snapshots)
            
            day3_snapshots = all_snapshots[(datetime_snapshots >= start_datetime) & (datetime_snapshots <= end_datetime)]
            
            if len(day3_snapshots) > 0:
                # Optimize only for day 3 (faster)
                network.optimize(
                    snapshots=day3_snapshots,
                    solver_name='gurobi',
                    solver_options={
                        'OptimalityTol': 1e-9,
                        'FeasibilityTol': 1e-9,
                        'IntFeasTol': 1e-9,
                    }
                )
                logger.info("Network optimized for day 3 (for Line losses)")
        
        # Now check for line losses
        if hasattr(network, 'lines_t') and hasattr(network.lines_t, 'p0') and hasattr(network.lines_t, 'p1'):
            # Get snapshots in day 3 range
            all_snapshots = network.snapshots
            if isinstance(all_snapshots, pd.MultiIndex):
                datetime_snapshots = pd.to_datetime([s[1] if isinstance(s, tuple) and len(s) >= 2 else s for s in all_snapshots])
            else:
                datetime_snapshots = pd.to_datetime(all_snapshots)
            
            day3_snapshots = all_snapshots[(datetime_snapshots >= start_datetime) & (datetime_snapshots <= end_datetime)]
            
            if len(day3_snapshots) > 0:
                # Get line power flows
                line_p0 = network.lines_t.p0.loc[day3_snapshots]  # Power at bus0
                line_p1 = network.lines_t.p1.loc[day3_snapshots]  # Power at bus1
                
                # Calculate losses for each line
                # In PyPSA DC power flow: when power flows from bus0 to bus1, p0 > 0 and p1 < 0
                # Losses = power sent - power received = p0 - (-p1) = p0 + p1
                # Since p1 is negative, losses = p0 - abs(p1) = abs(p0) - abs(p1)
                # For each line: losses = abs(abs(p0) - abs(p1))
                # Sum losses across all lines for each snapshot
                line_losses_per_snapshot = (line_p0.abs() - line_p1.abs()).abs().sum(axis=1)
                
                # Convert to DataFrame with DateTime
                if isinstance(day3_snapshots, pd.MultiIndex):
                    line_datetimes = pd.to_datetime([s[1] if isinstance(s, tuple) and len(s) >= 2 else s for s in day3_snapshots])
                else:
                    line_datetimes = pd.to_datetime(day3_snapshots)
                
                line_losses = pd.DataFrame({
                    'DateTime': line_datetimes,
                    'Line_Losses_MW': line_losses_per_snapshot.values
                })
                line_losses = line_losses.sort_values('DateTime')
                
                logger.info(f"Found Line transmission losses: {line_losses['Line_Losses_MW'].sum():.2f} MWh total")
                logger.info(f"  Mean: {line_losses['Line_Losses_MW'].mean():.2f} MW, "
                           f"Max: {line_losses['Line_Losses_MW'].max():.2f} MW, "
                           f"Min: {line_losses['Line_Losses_MW'].min():.2f} MW")
                
                # Add line losses to load
                pypsa_total_load = pd.merge(pypsa_total_load, line_losses, on='DateTime', how='outer')
                pypsa_total_load['Line_Losses_MW'] = pypsa_total_load['Line_Losses_MW'].fillna(0.0)
                pypsa_total_load['Total_Load_MW'] = pypsa_total_load['Total_Load_MW'] + pypsa_total_load['Line_Losses_MW']
                pypsa_total_load = pypsa_total_load[['DateTime', 'Total_Load_MW']].copy()
            else:
                logger.warning("No snapshots found in day 3 range for Line losses check")
        else:
            logger.info("Network not optimized or lines_t.p0/p1 not available (will optimize if needed)")
    else:
        logger.info("No Lines in network")
    
    # Calculate Sienna total generation (all carriers except 'load')
    sienna_generation = sienna_day3[sienna_day3['carrier'] != 'load'].copy()
    sienna_total_gen = sienna_generation.groupby('DateTime')['value'].sum().reset_index()
    sienna_total_gen.columns = ['DateTime', 'Total_Generation_MW']
    sienna_total_gen = sienna_total_gen.sort_values('DateTime')
    
    # Calculate Sienna total load (carrier == 'load', multiply by 100)
    sienna_load = sienna_day3[sienna_day3['carrier'] == 'load'].copy()
    sienna_total_load = sienna_load.groupby('DateTime')['value'].sum().reset_index()
    sienna_total_load['value'] = sienna_total_load['value'] * 100  # Convert to MW
    sienna_total_load.columns = ['DateTime', 'Total_Load_MW']
    sienna_total_load = sienna_total_load.sort_values('DateTime')
    
    # Calculate PyPSA total renewables for net load calculation
    pypsa_renewable_carriers = ['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'hydro', 'ror']
    pypsa_renewables = pypsa_day3[pypsa_day3['carrier'].isin(pypsa_renewable_carriers)].copy()
    pypsa_total_renewables = pypsa_renewables.groupby('DateTime')['value'].sum().reset_index()
    pypsa_total_renewables.columns = ['DateTime', 'Total_Renewables_MW']
    pypsa_total_renewables = pypsa_total_renewables.sort_values('DateTime')
    
    # Calculate battery charging (negative values = charging, consuming power)
    pypsa_battery = pypsa_day3[pypsa_day3['carrier'] == 'battery'].copy()
    if len(pypsa_battery) > 0:
        # Battery charging is when value is negative (consuming power)
        pypsa_battery_charging = pypsa_battery[pypsa_battery['value'] < 0].copy()
        pypsa_battery_charging['charging_mw'] = pypsa_battery_charging['value'].abs()  # Make positive for clarity
        pypsa_total_battery_charging = pypsa_battery_charging.groupby('DateTime')['charging_mw'].sum().reset_index()
        pypsa_total_battery_charging.columns = ['DateTime', 'Battery_Charging_MW']
        pypsa_total_battery_charging = pypsa_total_battery_charging.sort_values('DateTime')
    else:
        # No batteries, create empty series
        pypsa_total_battery_charging = pd.DataFrame(columns=['DateTime', 'Battery_Charging_MW'])
    
    # Merge to compare
    pypsa_comparison = pd.merge(pypsa_total_gen, pypsa_total_load, on='DateTime', how='outer')
    pypsa_comparison = pd.merge(pypsa_comparison, pypsa_total_renewables, on='DateTime', how='outer')
    pypsa_comparison = pd.merge(pypsa_comparison, pypsa_total_battery_charging, on='DateTime', how='outer')
    pypsa_comparison['Total_Renewables_MW'] = pypsa_comparison['Total_Renewables_MW'].fillna(0.0)
    pypsa_comparison['Battery_Charging_MW'] = pypsa_comparison['Battery_Charging_MW'].fillna(0.0)
    pypsa_comparison['Difference_MW'] = pypsa_comparison['Total_Generation_MW'] - pypsa_comparison['Total_Load_MW']
    # Net Load = Load - Renewables (the load that must be met by non-renewable generation)
    pypsa_comparison['Net_Load_MW'] = pypsa_comparison['Total_Load_MW'] - pypsa_comparison['Total_Renewables_MW']
    # Net Generation = Generation - Battery Charging (generation available to meet load)
    pypsa_comparison['Net_Generation_MW'] = pypsa_comparison['Total_Generation_MW'] - pypsa_comparison['Battery_Charging_MW']
    # Net Generation - Load difference
    pypsa_comparison['Net_Gen_Minus_Load_MW'] = pypsa_comparison['Net_Generation_MW'] - pypsa_comparison['Total_Load_MW']
    # Handle NaN values - if either is NaN, set difference to NaN and exceeds to False
    pypsa_comparison['Generation_Exceeds_Load'] = (
        ~pypsa_comparison['Difference_MW'].isna() & (pypsa_comparison['Difference_MW'] > 0.01)
    )  # 0.01 MW tolerance
    pypsa_comparison['Net_Gen_Exceeds_Load'] = (
        ~pypsa_comparison['Net_Gen_Minus_Load_MW'].isna() & (pypsa_comparison['Net_Gen_Minus_Load_MW'] > 0.01)
    )  # 0.01 MW tolerance
    
    sienna_comparison = pd.merge(sienna_total_gen, sienna_total_load, on='DateTime', how='outer')
    sienna_comparison['Difference_MW'] = sienna_comparison['Total_Generation_MW'] - sienna_comparison['Total_Load_MW']
    sienna_comparison['Generation_Exceeds_Load'] = sienna_comparison['Difference_MW'] > 0.01  # 0.01 MW tolerance
    
    # Print results
    logger.info("\n" + "=" * 80)
    logger.info("PYPSA POWER BALANCE (First 4 Days)")
    logger.info("=" * 80)
    logger.info(f"{'DateTime':<20} {'Gen (MW)':<12} {'Batt Chg (MW)':<15} {'Net Gen (MW)':<15} {'Load (MW)':<12} {'Net Gen-Load (MW)':<20} {'Exceeds?':<10}")
    logger.info("-" * 80)
    
    for _, row in pypsa_comparison.iterrows():
        exceeds = "YES" if row['Net_Gen_Exceeds_Load'] else "NO"
        gen_val = f"{row['Total_Generation_MW']:>11.2f}" if pd.notna(row['Total_Generation_MW']) else "        nan"
        batt_chg_val = f"{row['Battery_Charging_MW']:>14.2f}" if pd.notna(row['Battery_Charging_MW']) else "          nan"
        net_gen_val = f"{row['Net_Generation_MW']:>14.2f}" if pd.notna(row['Net_Generation_MW']) else "          nan"
        load_val = f"{row['Total_Load_MW']:>11.2f}" if pd.notna(row['Total_Load_MW']) else "        nan"
        net_gen_load_diff = f"{row['Net_Gen_Minus_Load_MW']:>19.2f}" if pd.notna(row['Net_Gen_Minus_Load_MW']) else "             nan"
        logger.info(f"{str(row['DateTime']):<20} {gen_val} {batt_chg_val} {net_gen_val} {load_val} {net_gen_load_diff} {exceeds:>10}")
    
    pypsa_exceeds_count = pypsa_comparison['Generation_Exceeds_Load'].sum()
    pypsa_net_gen_exceeds_count = pypsa_comparison['Net_Gen_Exceeds_Load'].sum()
    pypsa_total_hours = len(pypsa_comparison)
    pypsa_valid_diffs = pypsa_comparison['Difference_MW'].dropna()
    pypsa_valid_net_gen_diffs = pypsa_comparison['Net_Gen_Minus_Load_MW'].dropna()
    logger.info("\n" + "-" * 80)
    logger.info(f"PyPSA: Generation exceeds load in {pypsa_exceeds_count} out of {pypsa_total_hours} hours")
    logger.info(f"PyPSA: Net Generation (Gen - Batt Chg) exceeds load in {pypsa_net_gen_exceeds_count} out of {pypsa_total_hours} hours")
    if len(pypsa_valid_diffs) > 0:
        logger.info(f"PyPSA: Mean difference (Gen - Load): {pypsa_valid_diffs.mean():.2f} MW")
    if len(pypsa_valid_net_gen_diffs) > 0:
        logger.info(f"PyPSA: Mean difference (Net Gen - Load): {pypsa_valid_net_gen_diffs.mean():.2f} MW")
        logger.info(f"PyPSA: Total battery charging: {pypsa_comparison['Battery_Charging_MW'].sum():.2f} MWh")
        logger.info(f"PyPSA: Max difference: {pypsa_valid_diffs.max():.2f} MW")
        logger.info(f"PyPSA: Min difference: {pypsa_valid_diffs.min():.2f} MW")
    else:
        logger.warning("PyPSA: No valid differences (all NaN)")
    
    logger.info("\n" + "=" * 80)
    logger.info("SIENNA POWER BALANCE (First 4 Days)")
    logger.info("=" * 80)
    logger.info(f"{'DateTime':<20} {'Generation (MW)':<18} {'Load (MW)':<15} {'Difference (MW)':<18} {'Exceeds?':<10}")
    logger.info("-" * 80)
    
    for _, row in sienna_comparison.iterrows():
        exceeds = "YES" if row['Generation_Exceeds_Load'] else "NO"
        logger.info(f"{str(row['DateTime']):<20} {row['Total_Generation_MW']:>17.2f} {row['Total_Load_MW']:>14.2f} "
                   f"{row['Difference_MW']:>17.2f} {exceeds:>10}")
    
    sienna_exceeds_count = sienna_comparison['Generation_Exceeds_Load'].sum()
    sienna_total_hours = len(sienna_comparison)
    logger.info("\n" + "-" * 80)
    logger.info(f"Sienna: Generation exceeds load in {sienna_exceeds_count} out of {sienna_total_hours} hours")
    logger.info(f"Sienna: Mean difference: {sienna_comparison['Difference_MW'].mean():.2f} MW")
    logger.info(f"Sienna: Max difference: {sienna_comparison['Difference_MW'].max():.2f} MW")
    logger.info(f"Sienna: Min difference: {sienna_comparison['Difference_MW'].min():.2f} MW")
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    if pypsa_exceeds_count > 0:
        logger.warning(f"⚠️  PyPSA generation exceeds load in {pypsa_exceeds_count} hours!")
        logger.warning(f"   This suggests PyPSA allows generation > load (possibly via Links or other mechanisms)")
    else:
        logger.info("✓ PyPSA generation matches load (within tolerance)")
    
    if sienna_exceeds_count > 0:
        logger.warning(f"⚠️  Sienna generation exceeds load in {sienna_exceeds_count} hours!")
    else:
        logger.info("✓ Sienna generation matches load (within tolerance)")
    
    return pypsa_comparison, sienna_comparison


if __name__ == "__main__":
    plot_renewable_totals()

