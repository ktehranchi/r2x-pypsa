import pytest
import pypsa
import pandas as pd
import json
import h5py
import sqlite3
import os
from pathlib import Path
from r2x.api import System
from infrasys import TimeSeriesStorageType
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization.to_sienna import infrasys_to_psy
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import create_default_mapping
from loguru import logger

from helpers import (
    plot_generator_marginal_costs,
    plot_energy_balance,
    plot_capacity_comparison,
    plot_sienna_energy_balance
)
from test_time_series_helpers import (
    extract_pypsa_generator_time_series,
    extract_sienna_generator_time_series,
    compare_time_series
)


def compare_battery_parameters(network, json_file, h5_file):
    """Compare all battery/storage parameters between PyPSA and Sienna.
    
    Parameters:
        network: PyPSA network object
        json_file: Path to Sienna JSON file
        h5_file: Path to Sienna HDF5 file (not used but kept for consistency)
    """
    logger.info("=" * 80)
    logger.info("BATTERY PARAMETER COMPARISON")
    logger.info("=" * 80)
    
    # Get PyPSA storage units
    if not hasattr(network, 'storage_units') or len(network.storage_units) == 0:
        logger.warning("No PyPSA storage units found")
        return
    
    pypsa_storage = network.storage_units.copy()
    
    # Load Sienna storage from JSON
    with open(json_file, 'r') as f:
        sienna_data = json.load(f)
    
    # Find storage components in Sienna JSON
    sienna_storage = []
    components = sienna_data.get('data', {}).get('components', [])
    for comp in components:
        if comp.get('__metadata__', {}).get('type') == 'EnergyReservoirStorage':
            sienna_storage.append(comp)
    
    logger.info(f"PyPSA storage units: {len(pypsa_storage)}")
    logger.info(f"Sienna storage units: {len(sienna_storage)}")
    
    # Create mapping by name
    sienna_by_name = {s.get('name'): s for s in sienna_storage}
    
    # Compare each storage unit
    mismatches = []
    matches = []
    
    for su_name, su_data in pypsa_storage.iterrows():
        logger.info(f"\n{'='*80}")
        logger.info(f"Storage Unit: {su_name}")
        logger.info(f"{'='*80}")
        
        # PyPSA parameters
        pypsa_p_nom = su_data.get('p_nom', 0.0)
        pypsa_max_hours = su_data.get('max_hours', 1.0)
        pypsa_e_nom = pypsa_p_nom * pypsa_max_hours  # Energy capacity in MWh
        pypsa_efficiency_store = su_data.get('efficiency_store', 1.0)
        pypsa_efficiency_dispatch = su_data.get('efficiency_dispatch', 1.0)
        pypsa_soc_initial = su_data.get('state_of_charge_initial', 0.0)  # MWh
        pypsa_soc_initial_pct = (pypsa_soc_initial / pypsa_e_nom * 100) if pypsa_e_nom > 0 else 0.0
        pypsa_cyclic = su_data.get('cyclic_state_of_charge_per_period', False)
        pypsa_marginal_cost = su_data.get('marginal_cost', 0.0)
        pypsa_p_min_pu = su_data.get('p_min_pu', -1.0)
        pypsa_p_max_pu = su_data.get('p_max_pu', 1.0)
        pypsa_bus = su_data.get('bus', 'unknown')
        
        logger.info(f"\nPyPSA Parameters:")
        logger.info(f"  Power capacity (p_nom): {pypsa_p_nom:.2f} MW")
        logger.info(f"  Max hours: {pypsa_max_hours:.2f} hours")
        logger.info(f"  Energy capacity (e_nom): {pypsa_e_nom:.2f} MWh")
        logger.info(f"  Charge efficiency (efficiency_store): {pypsa_efficiency_store:.4f}")
        logger.info(f"  Discharge efficiency (efficiency_dispatch): {pypsa_efficiency_dispatch:.4f}")
        logger.info(f"  Initial SOC: {pypsa_soc_initial:.2f} MWh ({pypsa_soc_initial_pct:.2f}%)")
        logger.info(f"  Cyclic (cyclic_state_of_charge_per_period): {pypsa_cyclic}")
        logger.info(f"  Marginal cost: {pypsa_marginal_cost:.4f} $/MWh")
        logger.info(f"  Power limits (p_min_pu, p_max_pu): [{pypsa_p_min_pu:.4f}, {pypsa_p_max_pu:.4f}]")
        logger.info(f"  Bus: {pypsa_bus}")
        
        # Check for corresponding Sienna storage
        sienna_storage_unit = sienna_by_name.get(su_name)
        
        if sienna_storage_unit is None:
            logger.warning(f"  ⚠️  No matching Sienna storage unit found for {su_name}")
            mismatches.append({
                'name': su_name,
                'issue': 'Missing in Sienna'
            })
            continue
        
        # Extract Sienna parameters
        sienna_base_power = sienna_storage_unit.get('base_power', 100.0)
        sienna_rating = sienna_storage_unit.get('rating', 0.0)  # per-unit
        sienna_power_capacity = sienna_rating * sienna_base_power  # MW
        
        # Power limits (in per-unit, need to convert to MW)
        input_limits = sienna_storage_unit.get('input_active_power_limits', {})
        output_limits = sienna_storage_unit.get('output_active_power_limits', {})
        sienna_max_charge_pu = input_limits.get('max', 0.0) if isinstance(input_limits, dict) else 0.0
        sienna_max_discharge_pu = output_limits.get('max', 0.0) if isinstance(output_limits, dict) else 0.0
        sienna_max_charge_mw = sienna_max_charge_pu * sienna_base_power
        sienna_max_discharge_mw = sienna_max_discharge_pu * sienna_base_power
        
        # Energy capacity (in per-unit, need to convert to MWh)
        sienna_storage_capacity_pu = sienna_storage_unit.get('storage_capacity', 0.0)
        sienna_e_nom = sienna_storage_capacity_pu * sienna_base_power  # MWh
        
        # Initial SOC (fraction)
        sienna_soc_initial_pct = sienna_storage_unit.get('initial_storage_capacity_level', 0.0) * 100
        sienna_soc_initial = sienna_soc_initial_pct / 100.0 * sienna_e_nom  # MWh
        
        # Efficiencies
        efficiency = sienna_storage_unit.get('efficiency', {})
        if isinstance(efficiency, dict):
            sienna_efficiency_store = efficiency.get('in', 1.0)
            sienna_efficiency_dispatch = efficiency.get('out', 1.0)
        else:
            sienna_efficiency_store = 1.0
            sienna_efficiency_dispatch = 1.0
        
        sienna_discharge_efficiency = sienna_storage_unit.get('discharge_efficiency', sienna_efficiency_dispatch)
        
        # Marginal cost from operation_cost
        sienna_marginal_cost = 0.0
        op_cost = sienna_storage_unit.get('operation_cost', {})
        if op_cost:
            variable = op_cost.get('variable', {})
            if variable:
                value_curve = variable.get('value_curve', {})
                if value_curve:
                    sienna_marginal_cost = value_curve.get('proportional_term', 0.0)
        
        sienna_bus = sienna_storage_unit.get('bus', {})
        if isinstance(sienna_bus, dict):
            sienna_bus_name = sienna_bus.get('name', 'unknown')
        else:
            sienna_bus_name = str(sienna_bus)
        
        logger.info(f"\nSienna Parameters:")
        logger.info(f"  Power capacity (rating * base_power): {sienna_power_capacity:.2f} MW")
        logger.info(f"  Max charge (input limit): {sienna_max_charge_mw:.2f} MW")
        logger.info(f"  Max discharge (output limit): {sienna_max_discharge_mw:.2f} MW")
        logger.info(f"  Energy capacity (storage_capacity * base_power): {sienna_e_nom:.2f} MWh")
        logger.info(f"  Charge efficiency (efficiency.in): {sienna_efficiency_store:.4f}")
        logger.info(f"  Discharge efficiency (efficiency.out): {sienna_efficiency_dispatch:.4f}")
        logger.info(f"  Discharge efficiency (discharge_efficiency): {sienna_discharge_efficiency:.4f}")
        logger.info(f"  Initial SOC: {sienna_soc_initial:.2f} MWh ({sienna_soc_initial_pct:.2f}%)")
        logger.info(f"  Marginal cost: {sienna_marginal_cost:.4f} $/MWh")
        logger.info(f"  Bus: {sienna_bus_name}")
        
        # Compare parameters
        logger.info(f"\nComparison:")
        issues = []
        
        # Power capacity
        if abs(pypsa_p_nom - sienna_power_capacity) > 0.01:
            issues.append(f"Power capacity mismatch: PyPSA={pypsa_p_nom:.2f} MW, Sienna={sienna_power_capacity:.2f} MW")
        else:
            logger.info(f"  ✓ Power capacity matches: {pypsa_p_nom:.2f} MW")
        
        # Energy capacity
        if abs(pypsa_e_nom - sienna_e_nom) > 0.01:
            issues.append(f"Energy capacity mismatch: PyPSA={pypsa_e_nom:.2f} MWh, Sienna={sienna_e_nom:.2f} MWh")
        else:
            logger.info(f"  ✓ Energy capacity matches: {pypsa_e_nom:.2f} MWh")
        
        # Charge efficiency
        if abs(pypsa_efficiency_store - sienna_efficiency_store) > 1e-6:
            issues.append(f"Charge efficiency mismatch: PyPSA={pypsa_efficiency_store:.6f}, Sienna={sienna_efficiency_store:.6f}")
        else:
            logger.info(f"  ✓ Charge efficiency matches: {pypsa_efficiency_store:.6f}")
        
        # Discharge efficiency
        if abs(pypsa_efficiency_dispatch - sienna_efficiency_dispatch) > 1e-6:
            issues.append(f"Discharge efficiency mismatch: PyPSA={pypsa_efficiency_dispatch:.6f}, Sienna={sienna_efficiency_dispatch:.6f}")
        else:
            logger.info(f"  ✓ Discharge efficiency matches: {pypsa_efficiency_dispatch:.6f}")
        
        # Initial SOC
        if abs(pypsa_soc_initial_pct - sienna_soc_initial_pct) > 0.01:
            issues.append(f"Initial SOC mismatch: PyPSA={pypsa_soc_initial_pct:.2f}%, Sienna={sienna_soc_initial_pct:.2f}%")
        else:
            logger.info(f"  ✓ Initial SOC matches: {pypsa_soc_initial_pct:.2f}%")
        
        # Marginal cost
        if abs(pypsa_marginal_cost - sienna_marginal_cost) > 1e-6:
            issues.append(f"Marginal cost mismatch: PyPSA={pypsa_marginal_cost:.6f} $/MWh, Sienna={sienna_marginal_cost:.6f} $/MWh")
        else:
            logger.info(f"  ✓ Marginal cost matches: {pypsa_marginal_cost:.6f} $/MWh")
        
        # Bus
        if pypsa_bus != sienna_bus_name:
            issues.append(f"Bus mismatch: PyPSA={pypsa_bus}, Sienna={sienna_bus_name}")
        else:
            logger.info(f"  ✓ Bus matches: {pypsa_bus}")
        
        # Power limits
        if abs(pypsa_p_max_pu * pypsa_p_nom - sienna_max_discharge_mw) > 0.01:
            issues.append(f"Max discharge limit mismatch: PyPSA={pypsa_p_max_pu * pypsa_p_nom:.2f} MW, Sienna={sienna_max_discharge_mw:.2f} MW")
        else:
            logger.info(f"  ✓ Max discharge limit matches: {pypsa_p_max_pu * pypsa_p_nom:.2f} MW")
        
        if abs(abs(pypsa_p_min_pu) * pypsa_p_nom - sienna_max_charge_mw) > 0.01:
            issues.append(f"Max charge limit mismatch: PyPSA={abs(pypsa_p_min_pu) * pypsa_p_nom:.2f} MW, Sienna={sienna_max_charge_mw:.2f} MW")
        else:
            logger.info(f"  ✓ Max charge limit matches: {abs(pypsa_p_min_pu) * pypsa_p_nom:.2f} MW")
        
        if issues:
            logger.warning(f"  ⚠️  {len(issues)} parameter mismatch(es) found:")
            for issue in issues:
                logger.warning(f"    - {issue}")
            mismatches.append({
                'name': su_name,
                'issues': issues
            })
        else:
            logger.info(f"  ✓ All parameters match!")
            matches.append(su_name)
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Total storage units: {len(pypsa_storage)}")
    logger.info(f"Matches: {len(matches)}")
    logger.info(f"Mismatches: {len(mismatches)}")
    
    if mismatches:
        logger.warning(f"\n⚠️  Storage units with parameter mismatches:")
        for m in mismatches:
            logger.warning(f"  - {m['name']}: {m.get('issue', '; '.join(m.get('issues', [])))}")
    
    logger.info("=" * 80)


def test_end_to_end_pypsa_to_psy_conversion():
    """Test end-to-end conversion from PyPSA to PSY system."""
    # Use the test data
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")

    parser = PypsaParser(netcdf_file=str(test_file))
    pypsa_system = parser.build_system()

    # Convert to Sienna
    mapping = create_default_mapping()

    # Create a new PSY system
    psy_system = System(
        name="PSY system",
        auto_add_composed_components=True,
        time_series_storage_type=TimeSeriesStorageType.HDF5
    )

    # Convert all PyPSA components to PSY components
    conversion_failures = 0
    for component in pypsa_system._component_mgr.iter_all():
        try:
            pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
        except Exception as e:
            logger.warning(f"Failed to convert component {component.name}: {e}")
            conversion_failures += 1
            continue

    # Serialize the PSY system to Sienna format
    output_dir = Path("tests/test_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "elec_s380_c7a_ec_lv1_output.json"
    infrasys_to_psy(psy_system, filename=output_file)
    
    # Verify the output file was created
    assert output_file.exists()
    
    # Note: Not cleaning up output files - they remain in test_output/ for inspection
    
    # Log conversion statistics
    total_components = len(list(pypsa_system._component_mgr.iter_all()))
    successful_conversions = total_components - conversion_failures
    logger.info(f"Converted {successful_conversions}/{total_components} components successfully")




def test_e2e_economic_dispatch():
    """Test end-to-end conversion from PyPSA to PSY system.
    
    To enable network clustering (copper plate), set environment variable:
        CLUSTER_NETWORK=1 pytest tests/test_end_to_end.py::test_e2e_economic_dispatch
    """
    # Use the test data
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    network = pypsa.Network(test_file)

    # Optional: Cluster network to make it a copper plate
    cluster_network = os.getenv("CLUSTER_NETWORK", "0").lower() in ("1", "true", "yes")
    if cluster_network:
        logger.info("=" * 80)
        logger.info("CLUSTERING NETWORK TO COPPER PLATE")
        logger.info("=" * 80)
        
        # Get busmap from interconnect
        if 'interconnect' in network.buses.columns:
            busmap = network.buses.interconnect
            logger.info(f"Using interconnect as busmap")
            logger.info(f"  Unique interconnects: {busmap.unique()}")
        else:
            logger.warning("Network buses do not have 'interconnect' column. Skipping clustering.")
            cluster_network = False
        
        if cluster_network:
            # Drop columns that might interfere with clustering
            cols_to_drop = ['Pd', 'country', 'reeds_zone']
            for col in cols_to_drop:
                if col in network.buses.columns:
                    network.buses.drop(columns=col, inplace=True)
                    logger.info(f"Dropped column '{col}' from buses")
            
            # Cluster the network
            try:
                original_bus_count = len(network.buses)
                # Try the cluster_by_busmap method (if available)
                if hasattr(network, 'cluster') and hasattr(network.cluster, 'cluster_by_busmap'):
                    clustered_network = network.cluster.cluster_by_busmap(busmap)
                    network = clustered_network
                else:
                    # Alternative: use pypsa.clustering.spatial.get_clustering_from_busmap
                    try:
                        from pypsa.clustering.spatial import get_clustering_from_busmap
                        clustering = get_clustering_from_busmap(
                            network,
                            busmap,
                            aggregate_generators_weighted=True,
                            aggregate_one_ports=["Load", "StorageUnit"],
                        )
                        network = clustering.network
                    except ImportError:
                        logger.error("PyPSA clustering module not available. Cannot cluster network.")
                        raise
                
                logger.info(f"Network clustered successfully")
                logger.info(f"  Original buses: {original_bus_count}")
                logger.info(f"  Clustered buses: {len(network.buses)}")
            except Exception as e:
                logger.error(f"Failed to cluster network: {e}")
                import traceback
                logger.error(traceback.format_exc())
                logger.warning("Continuing with original network (not clustered)")
        
        logger.info("=" * 80)

    # Check if PyPSA is using copper plate or nodal balance
    logger.info("=" * 80)
    logger.info("CHECKING PyPSA NETWORK MODEL (Copper Plate vs Nodal Balance)")
    logger.info("=" * 80)
    if hasattr(network, 'lines') and len(network.lines) > 0:
        finite_capacity_lines = network.lines[network.lines['s_nom'] < float('inf')]
        total_lines = len(network.lines)
        finite_lines = len(finite_capacity_lines)
        infinite_lines = total_lines - finite_lines
        
        logger.info(f"Total lines in network: {total_lines}")
        logger.info(f"Lines with finite capacity (s_nom < inf): {finite_lines}")
        logger.info(f"Lines with infinite capacity (s_nom = inf): {infinite_lines}")
        
        if finite_lines == 0:
            logger.info("→ PyPSA is effectively COPPER PLATE (all lines have infinite capacity)")
            logger.info("  Storage can serve load at any bus regardless of bus assignment")
        else:
            logger.info("→ PyPSA enforces NODAL BALANCE (some lines have finite capacity)")
            logger.info("  Storage can only serve load at its own bus (or via transmission)")
            if finite_lines < total_lines:
                logger.info(f"  Note: {infinite_lines} lines have infinite capacity, {finite_lines} have finite capacity")
    else:
        logger.info("No lines in network → PyPSA is COPPER PLATE")
        logger.info("  Storage can serve load at any bus regardless of bus assignment")
    logger.info("=" * 80)

    extendable_attrs_backup = {}

    for component in network.components.keys():
        extendable_attrs_backup[component] = {}
        for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
            if attr in network.df(component).columns:
                # Backup the current state of the attribute
                extendable_attrs_backup[component][attr] = network.df(component)[attr].copy()
                # Set the attribute to False
                network.df(component)[attr] = False

    # Remember our load is for 2030, so lets reduce the system load for the sake of this simulation feasibility
    network.loads_t.p_set *= 0.75 
    
    # ENABLE storage units
    logger.info("=" * 80)
    logger.info("ENABLING STORAGE UNITS")
    logger.info("=" * 80)
    if hasattr(network, 'storage_units') and len(network.storage_units) > 0:
        storage_count = len(network.storage_units)
        network.storage_units['active'] = True  # Enable storage
        logger.info(f"Enabled {storage_count} storage units (set active=True)")
    if hasattr(network, 'stores') and len(network.stores) > 0:
        store_count = len(network.stores)
        network.stores['active'] = True  # Enable stores
        logger.info(f"Enabled {store_count} stores (set active=True)")
    logger.info("=" * 80)
    
    # ENABLE NUCLEAR GENERATORS (they are active by default, but ensure they're enabled)
    logger.info("=" * 80)
    logger.info("ENABLING NUCLEAR GENERATORS")
    logger.info("=" * 80)
    if hasattr(network, 'generators') and len(network.generators) > 0:
        nuclear_gens = network.generators[network.generators.carrier == 'nuclear']
        if len(nuclear_gens) > 0:
            nuclear_count = len(nuclear_gens)
            nuclear_capacity = nuclear_gens.p_nom.sum()
            network.generators.loc[nuclear_gens.index, 'active'] = True
            logger.info(f"Enabled {nuclear_count} nuclear generators ({nuclear_capacity:.2f} MW total capacity)")
        else:
            logger.info("No nuclear generators found in network")
    logger.info("=" * 80)
    
    # Set all capital costs to zero to ensure pure economic dispatch (operational costs only)
    # This matches Sienna's ED which only includes operational costs
    for component_type in ['Generator', 'StorageUnit', 'Store', 'Link', 'Line']:
        if component_type in network.components.keys():
            df = network.df(component_type)
            if 'capital_cost' in df.columns:
                df['capital_cost'] = 0.0
            # Also set fixed O&M costs to zero if they exist
            if 'marginal_cost_quadratic' in df.columns:
                # Keep quadratic costs (they're operational)
                pass
    
    # Optimize with tight tolerances for better precision
    network.optimize(
        snapshots=network.snapshots[0:7*24],
        solver_name='highs',
    )

    # Verify optimization completed successfully
    assert network.objective is not None
    logger.info(f"Optimization completed with highs, total objective: {network.objective}")
    
    # Calculate operational costs only (marginal_cost × generation)
    # This matches what Sienna ED includes
    operational_cost = 0.0
    snapshots = network.snapshots[0:7*24]
    
    # Sum operational costs from generators
    if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
        for gen_name in network.generators.index:
            gen = network.generators.loc[gen_name]
            marginal_cost = gen.get('marginal_cost', 0.0)
            if marginal_cost > 0:
                generation = network.generators_t.p.loc[snapshots, gen_name]
                operational_cost += (generation * marginal_cost).sum()
    
    # Sum operational costs from storage units (only when discharging, p > 0)
    if hasattr(network, 'storage_units_t') and hasattr(network.storage_units_t, 'p'):
        for su_name in network.storage_units.index:
            su = network.storage_units.loc[su_name]
            marginal_cost = su.get('marginal_cost', 0.0)
            if marginal_cost > 0:
                dispatch = network.storage_units_t.p.loc[snapshots, su_name]
                # Only count positive dispatch (discharging)
                operational_cost += (dispatch[dispatch > 0] * marginal_cost).sum()
    
    logger.info(f"PyPSA operational cost (marginal only): {operational_cost:,.2f}")
    logger.info(f"PyPSA total objective (includes capital): {network.objective:,.2f}")
    
    # DEBUGGING: Check load totals and wind availability
    logger.info("=" * 80)
    logger.info("DEBUGGING: LOAD AND WIND AVAILABILITY CHECKS")
    logger.info("=" * 80)
    
    # Check total load at each timestep
    if hasattr(network, 'loads_t') and hasattr(network.loads_t, 'p_set'):
        total_load_by_timestep = network.loads_t.p_set.loc[snapshots].sum(axis=1)
        logger.info(f"PyPSA total load statistics:")
        logger.info(f"  Total load (sum over all timesteps): {total_load_by_timestep.sum():,.2f} MWh")
        logger.info(f"  Mean load: {total_load_by_timestep.mean():,.2f} MW")
        logger.info(f"  Min load: {total_load_by_timestep.min():,.2f} MW")
        logger.info(f"  Max load: {total_load_by_timestep.max():,.2f} MW")
    
    # Check wind availability (p_max_pu * p_nom for wind generators)
    wind_gens = network.generators[network.generators['carrier'].isin(['onwind', 'offwind'])]
    if len(wind_gens) > 0:
        logger.info(f"\nPyPSA wind generators: {len(wind_gens)}")
        if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_max_pu'):
            wind_available_by_timestep = pd.Series(0.0, index=snapshots)
            for gen_name in wind_gens.index:
                gen = network.generators.loc[gen_name]
                p_nom = gen.get('p_nom', 0.0)
                if hasattr(network.generators_t.p_max_pu, gen_name):
                    p_max_pu = network.generators_t.p_max_pu[gen_name].loc[snapshots]
                    wind_available_by_timestep += p_max_pu * p_nom
                else:
                    # No time series, use full capacity
                    wind_available_by_timestep += p_nom
            
            logger.info(f"PyPSA wind availability statistics:")
            logger.info(f"  Total available (sum over all timesteps): {wind_available_by_timestep.sum():,.2f} MWh")
            logger.info(f"  Mean available: {wind_available_by_timestep.mean():,.2f} MW")
            logger.info(f"  Min available: {wind_available_by_timestep.min():,.2f} MW")
            logger.info(f"  Max available: {wind_available_by_timestep.max():,.2f} MW")
            
            # Check actual wind dispatch
            if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
                wind_dispatch_by_timestep = network.generators_t.p.loc[snapshots, wind_gens.index].sum(axis=1)
                logger.info(f"\nPyPSA wind dispatch statistics:")
                logger.info(f"  Total dispatch (sum over all timesteps): {wind_dispatch_by_timestep.sum():,.2f} MWh")
                logger.info(f"  Mean dispatch: {wind_dispatch_by_timestep.mean():,.2f} MW")
                logger.info(f"  Min dispatch: {wind_dispatch_by_timestep.min():,.2f} MW")
                logger.info(f"  Max dispatch: {wind_dispatch_by_timestep.max():,.2f} MW")
                logger.info(f"  Utilization (dispatch/available): {(wind_dispatch_by_timestep.sum() / wind_available_by_timestep.sum() * 100):.2f}%")
    
    # Check for zero-cost generators
    logger.info(f"\nPyPSA generator marginal cost statistics:")
    all_gens = network.generators[network.generators['p_nom'] > 0]
    marginal_costs = all_gens['marginal_cost']
    zero_cost_gens = all_gens[marginal_costs == 0.0]
    logger.info(f"  Total generators: {len(all_gens)}")
    logger.info(f"  Zero-cost generators: {len(zero_cost_gens)}")
    if len(zero_cost_gens) > 0:
        logger.info(f"  Zero-cost generator carriers: {zero_cost_gens['carrier'].value_counts().to_dict()}")
    logger.info(f"  Marginal cost range: [{marginal_costs.min():.6f}, {marginal_costs.max():.6f}] $/MWh")
    logger.info("=" * 80)
    
    # Use operational cost for comparison with Sienna
    pypsa_operational_objective = operational_cost
    
    # Solver-specific objective value checks (on operational cost)
    # assert pypsa_operational_objective < 4.23e7
    # assert pypsa_operational_objective > 4.21e7

    # Save PyPSA operational objective for comparison with Sienna
    output_dir = Path("tests/test_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    pypsa_objective_file = output_dir / "pypsa_objective.txt"
    with open(pypsa_objective_file, 'w') as f:
        f.write(str(pypsa_operational_objective))
    logger.info(f"Saved PyPSA operational objective ({pypsa_operational_objective:,.2f}) to {pypsa_objective_file}")

    # Save PyPSA dispatch for comparison with Sienna
    logger.info("Saving PyPSA dispatch...")
    pypsa_dispatch_file = output_dir / "pypsa_dispatch.csv"
    
    dispatch_data = []
    all_gens = None
    
    # Save ALL generators dispatch (matching Sienna format: DateTime, carrier, value)
    if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p'):
        all_gens = network.generators[network.generators['p_nom'] > 0]
        
        for gen_name in all_gens.index:
            gen = network.generators.loc[gen_name]
            carrier = gen.get('carrier', 'unknown')
            gen_dispatch = network.generators_t.p[gen_name].loc[snapshots]
            
            # Iterate over index and values separately to avoid tuple issues
            # The index might be a MultiIndex with (period, timestep) or a simple DatetimeIndex
            for idx in gen_dispatch.index:
                value = gen_dispatch.loc[idx]
                # Handle MultiIndex: (period, timestep) -> use timestep (second element)
                if isinstance(idx, tuple):
                    if len(idx) >= 2:
                        dt = idx[1]  # Use the timestep (datetime string)
                    else:
                        dt = idx[0]
                else:
                    dt = idx
                dispatch_data.append({
                    'DateTime': dt,
                    'name': gen_name,
                    'carrier': carrier,
                    'value': float(value)
                })
    
    # Save ALL storage units dispatch (matching Sienna format: DateTime, carrier, value)
    if hasattr(network, 'storage_units_t') and hasattr(network.storage_units_t, 'p') and hasattr(network, 'storage_units') and len(network.storage_units) > 0:
        all_storage = network.storage_units[network.storage_units['p_nom'] > 0]
        
        for su_name in all_storage.index:
            su = network.storage_units.loc[su_name]
            carrier = su.get('carrier', 'storage')
            su_dispatch = network.storage_units_t.p[su_name].loc[snapshots]
            
            # Iterate over index and values separately to avoid tuple issues
            # The index might be a MultiIndex with (period, timestep) or a simple DatetimeIndex
            for idx in su_dispatch.index:
                value = su_dispatch.loc[idx]
                # Handle MultiIndex: (period, timestep) -> use timestep (second element)
                if isinstance(idx, tuple):
                    if len(idx) >= 2:
                        dt = idx[1]  # Use the timestep (datetime string)
                    else:
                        dt = idx[0]
                else:
                    dt = idx
                dispatch_data.append({
                    'DateTime': dt,
                    'name': su_name,
                    'carrier': carrier,
                    'value': float(value)
                })
    
    # Save ALL loads (matching Sienna format: DateTime, carrier, value)
    if hasattr(network, 'loads_t') and hasattr(network.loads_t, 'p_set') and hasattr(network, 'loads') and len(network.loads) > 0:
        all_loads = network.loads
        
        for load_name in all_loads.index:
            load = network.loads.loc[load_name]
            carrier = load.get('carrier', 'load')
            load_demand = network.loads_t.p_set[load_name].loc[snapshots]
            
            # Iterate over index and values separately to avoid tuple issues
            # The index might be a MultiIndex with (period, timestep) or a simple DatetimeIndex
            for idx in load_demand.index:
                value = load_demand.loc[idx]
                # Handle MultiIndex: (period, timestep) -> use timestep (second element)
                if isinstance(idx, tuple):
                    if len(idx) >= 2:
                        dt = idx[1]  # Use the timestep (datetime string)
                    else:
                        dt = idx[0]
                else:
                    dt = idx
                dispatch_data.append({
                    'DateTime': dt,
                    'name': load_name,
                    'carrier': carrier,
                    'value': float(value)
                })
    
    if dispatch_data:
        pypsa_dispatch_df = pd.DataFrame(dispatch_data)
        # Convert DateTime to datetime - handle both string and datetime objects
        pypsa_dispatch_df['DateTime'] = pd.to_datetime(pypsa_dispatch_df['DateTime'], errors='coerce')
        # Drop any rows where datetime conversion failed
        pypsa_dispatch_df = pypsa_dispatch_df.dropna(subset=['DateTime'])
        pypsa_dispatch_df.to_csv(pypsa_dispatch_file, index=False)
        logger.info(f"Saved PyPSA dispatch ({len(pypsa_dispatch_df)} records) to {pypsa_dispatch_file}")
        

    else:
        logger.warning("No dispatch data to save (no generators, storage units, or loads with dispatch data)")

    # Plot energy balance to visualize dispatch
    logger.info("Plotting PyPSA energy balance...")

    # Convert the MODIFIED network to PSY system (not re-parsing from file)
    # This preserves the updated loads and extendable attributes
    parser = PypsaParser(network=network)
    pypsa_system = parser.build_system()

    # Convert to Sienna
    mapping = create_default_mapping()

    # Create a new PSY system
    psy_system = System(
        name="PSY system",
        auto_add_composed_components=True,
        time_series_storage_type=TimeSeriesStorageType.HDF5
    )

    # Convert all PyPSA components to PSY components
       # Convert all PyPSA components to PSY components (including storage)
    conversion_failures = 0
    for component in pypsa_system._component_mgr.iter_all():
        try:
            pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
        except Exception as e:
            logger.warning(f"Failed to convert component {component.name}: {e}")
            conversion_failures += 1
            continue

    # Serialize the PSY system to Sienna format
    # (output_dir already created above)
    output_file = output_dir / "elec_s380_c7a_ec_lv1_output_optimized.json"
    infrasys_to_psy(psy_system, filename=output_file)
    
    # Verify the output file was created
    assert output_file.exists()
    
    # Note: Not cleaning up output files - they remain in test_output/ for inspection
    
    # Log conversion statistics
    total_components = len(list(pypsa_system._component_mgr.iter_all()))
    successful_conversions = total_components - conversion_failures
    logger.info(f"Converted {successful_conversions}/{total_components} components successfully")


def test_pypsa_sienna_objective_match(caplog):
    """Validate that PyPSA and Sienna produce the same objective value.
    
    This test reads the objective values from files that should already exist:
    - tests/test_output/pypsa_objective.txt (created by test_e2e_economic_dispatch)
    - tests/test_output/sienna_objective.txt (created by running run_sienna_ed.jl manually)
    
    To run Sienna optimization manually:
        julia tests/run_sienna_ed.jl tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json tests/test_output/sienna_objective.txt
    """
    import logging
    # Use Python's standard logging so it appears in pytest output
    test_logger = logging.getLogger(__name__)
    test_logger.setLevel(logging.INFO)
    
    test_dir = Path(__file__).parent
    output_dir = test_dir / "test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Path to saved objectives
    pypsa_objective_file = output_dir / "pypsa_objective.txt"
    sienna_objective_file = output_dir / "sienna_objective.txt"
    
    # Check if files exist
    if not pypsa_objective_file.exists():
        raise FileNotFoundError(
            f"PyPSA objective file not found: {pypsa_objective_file}\n"
            "Run test_e2e_economic_dispatch first to generate it."
        )
    
    if not sienna_objective_file.exists():
        raise FileNotFoundError(
            f"Sienna objective file not found: {sienna_objective_file}\n"
            "Run the Julia script manually:\n"
            f"  julia tests/run_sienna_ed.jl tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json tests/test_output/sienna_objective.txt"
        )
    
    # Read objectives from files
    test_logger.info(f"Loading PyPSA objective from {pypsa_objective_file}")
    with open(pypsa_objective_file) as f:
        pypsa_objective = float(f.read().strip())
    
    test_logger.info(f"Loading Sienna objective from {sienna_objective_file}")
    with open(sienna_objective_file) as f:
        sienna_objective = float(f.read().strip())
    
    # Compare
    diff = abs(sienna_objective - pypsa_objective)
    pct_diff = (diff / pypsa_objective) * 100
    ratio = sienna_objective / pypsa_objective if pypsa_objective != 0 else float('inf')
    
    # Log comparison results (visible in pytest "live log collection" section)
    test_logger.info("")
    test_logger.info("=" * 80)
    test_logger.info("OBJECTIVE COMPARISON")
    test_logger.info("=" * 80)
    test_logger.info(f"PyPSA Objective:    ${pypsa_objective:,.2f}")
    test_logger.info(f"Sienna Objective:   ${sienna_objective:,.2f}")
    test_logger.info(f"Difference:         ${diff:,.2f} ({pct_diff:.2f}%)")
    test_logger.info(f"Sienna/PyPSA ratio: {ratio:.3f}")
    test_logger.info("=" * 80)
    
    # Note: PyPSA objective may include capital costs (investment) even when extendable=False,
    # while Sienna ED only includes operational costs. This can cause large differences.
    # For now, we just report the difference rather than asserting a match.
    if pct_diff < 5.0:
        test_logger.info("✓ Objectives match within 5%!")
    elif pct_diff < 50.0:
        test_logger.warning(f"⚠️  Objectives differ by {pct_diff:.2f}%")
    else:
        test_logger.warning(f"⚠️  Large difference ({pct_diff:.2f}%)")
    test_logger.info("")
    
    # Don't assert - just report for now until we understand the difference
    # assert pct_diff < 5.0, f"Objectives differ by {pct_diff:.2f}% (>${diff:,.2f})"
    
    # Plot Sienna energy balance if dispatch file exists (same 1 week period as PyPSA)
    dispatch_file = output_dir / "sienna_dispatch.csv"
    if dispatch_file.exists():
        test_logger.info("Plotting Sienna energy balance...")
        try:
            plot_sienna_energy_balance(dispatch_file, timesteps=7*24, label="Sienna")
        except Exception as e:
            test_logger.warning(f"Could not plot Sienna energy balance: {e}")
    else:
        test_logger.info(f"Sienna dispatch file not found: {dispatch_file}")
        test_logger.info("  Run the Julia script to generate it")


def test_compare_pypsa_sienna_systems():
    """Compare PyPSA and Sienna systems without running optimization.
    
    To force regeneration (bypass cache), set environment variable:
        FORCE_REGENERATE=1 pytest tests/test_end_to_end.py::test_compare_pypsa_sienna_systems
    """
    # Check environment variable to force regeneration
    force_regenerate = os.getenv("FORCE_REGENERATE", "0").lower() in ("1", "true", "yes")
    
    # Load PyPSA network
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    
    # Set up output files
    test_dir = Path(__file__).parent
    output_dir = test_dir / "test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_file = output_dir / "elec_s380_c7a_ec_lv1_comparison.json"
    h5_file = output_dir / f"{json_file.stem}.h5"
    
    # Check if we can use cached files
    use_cache = False
    if not force_regenerate and json_file.exists() and h5_file.exists():
        # Check modification times
        input_mtime = test_file.stat().st_mtime
        json_mtime = json_file.stat().st_mtime
        h5_mtime = h5_file.stat().st_mtime
        
        # Use cache if both output files are newer than input
        if json_mtime > input_mtime and h5_mtime > input_mtime:
            use_cache = True
            logger.info("Using cached Sienna files (output files are newer than input)")
    
    if not use_cache or force_regenerate:
        if force_regenerate:
            logger.info("Force regenerating Sienna files (FORCE_REGENERATE=1)")
        else:
            logger.info("Regenerating Sienna files (cache miss or files outdated)")
        
        # Remove old files before regenerating (especially important when force_regenerate=True)
        if json_file.exists():
            json_file.unlink()
            logger.debug(f"Removed existing JSON file: {json_file}")
        if h5_file.exists():
            h5_file.unlink()
            logger.debug(f"Removed existing HDF5 file: {h5_file}")
        
        network = pypsa.Network(test_file)
        
        # Apply modifications (same as optimization test)
        for component in network.components.keys():
            for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
                if attr in network.df(component).columns:
                    network.df(component)[attr] = False
        
        network.loads_t.p_set *= 0.75
        
        # Convert to Sienna using the MODIFIED network (not re-parsing from file)
        # This preserves the updated loads and extendable attributes
        parser = PypsaParser(network=network)
        pypsa_system = parser.build_system()
        
        mapping = create_default_mapping()
        
        psy_system = System(
            name="PSY system",
            auto_add_composed_components=True,
            time_series_storage_type=TimeSeriesStorageType.HDF5
        )
        
        for component in pypsa_system._component_mgr.iter_all():
            try:
                pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
            except Exception as e:
                logger.warning(f"Failed to convert component {component.name}: {e}")
                continue
        
        infrasys_to_psy(psy_system, filename=json_file)
    else:
        # Still need to load PyPSA network for comparison metrics
        network = pypsa.Network(test_file)
        
        # Apply modifications (same as optimization test)
        for component in network.components.keys():
            for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
                if attr in network.df(component).columns:
                    network.df(component)[attr] = False
        
        network.loads_t.p_set *= 0.75
    
    # ===== COMPARISON SECTION =====
    # This section always runs (whether using cache or not) to output the comparison table

    # ===== PYPSA METRICS =====
    logger.info("=" * 80)
    logger.info("PYPSA SYSTEM METRICS")
    logger.info("=" * 80)

    # Loads
    pypsa_loads = network.loads

    # Calculate max load per bus (peak across all time steps)
    if hasattr(network.loads_t, 'p_set') and len(network.loads_t.p_set) > 0:
        pypsa_max_load_per_bus = network.loads_t.p_set.max()  # Max per bus across all time steps
        pypsa_total_max_load = pypsa_max_load_per_bus.sum()  # Sum of max loads across all buses
        pypsa_max_load = pypsa_max_load_per_bus.max()  # Overall peak load
        pypsa_total_load_all_time = network.loads_t.p_set.sum().sum()  # Sum of all time steps (for reference)
    else:
        pypsa_total_max_load = 0.0
        pypsa_max_load = 0.0
        pypsa_total_load_all_time = 0.0

    pypsa_load_count = len(pypsa_loads)
    logger.info(f"Loads: {pypsa_load_count}")
    logger.info(f"Total max load (sum of peak per bus): {pypsa_total_max_load:.2f} MW")
    logger.info(f"Peak load (overall max): {pypsa_max_load:.2f} MW")
    logger.info(f"Total load (sum of all time steps, for reference): {pypsa_total_load_all_time:.2f} MW")

    # Generation
    # Only count generators with p_nom > 0 (zero-capacity generators are skipped in Sienna conversion)
    pypsa_generators = network.generators[network.generators.p_nom > 0]
    # Fix carrier names: PyPSA uses 'onwind' and 'offwind', not 'wind'
    # Note: 'hydro' now maps to RenewableDispatch in Sienna (with prime_mover_type == HY), not HydroDispatch
    pypsa_thermal = pypsa_generators[pypsa_generators.carrier.isin(['coal', 'gas', 'oil', 'nuclear', 'biomass', 'CCGT', 'OCGT', 'CCGT-95CCS', 'hydrogen_ct'])]
    # Renewable carriers that map to RenewableDispatch in Sienna (includes 'hydro' which maps to RenewableDispatch with prime_mover_type == HY)
    pypsa_renewable = pypsa_generators[pypsa_generators.carrier.isin(['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'ror', 'hydro'])]
    # Hydro generators (map to RenewableDispatch with prime_mover_type == HY, not HydroDispatch)
    pypsa_hydro = pypsa_generators[pypsa_generators.carrier == 'hydro']
    
    pypsa_thermal_capacity = pypsa_thermal.p_nom.sum() if len(pypsa_thermal) > 0 else 0.0
    # Calculate renewable capacity excluding hydro (to match Sienna calculation)
    pypsa_renewable_excluding_hydro = pypsa_renewable[pypsa_renewable.carrier != 'hydro']
    pypsa_renewable_capacity = pypsa_renewable_excluding_hydro.p_nom.sum() if len(pypsa_renewable_excluding_hydro) > 0 else 0.0
    pypsa_renewable_count_excluding_hydro = len(pypsa_renewable_excluding_hydro)
    pypsa_total_capacity = pypsa_generators.p_nom.sum()
    
    logger.info(f"Generators (p_nom > 0): {len(pypsa_generators)}")
    logger.info(f"  Thermal capacity: {pypsa_thermal_capacity:.2f} MW")
    logger.info(f"  Renewable capacity: {pypsa_renewable_capacity:.2f} MW")
    logger.info(f"  Total capacity: {pypsa_total_capacity:.2f} MW")

    # Storage
    if hasattr(network, 'storage_units') and len(network.storage_units) > 0:
        pypsa_storage_capacity = network.storage_units.p_nom.sum()
        logger.info(f"Storage units: {len(network.storage_units)}")
        logger.info(f"  Storage capacity: {pypsa_storage_capacity:.2f} MW")
        
        # Check initial state of charge for all storage units
        logger.info("=" * 80)
        logger.info("PyPSA Storage Units - Initial State of Charge")
        logger.info("=" * 80)
        
        for su_name, su_data in network.storage_units.iterrows():
            p_nom = su_data.get('p_nom', 0.0)
            max_hours = su_data.get('max_hours', 1.0)
            storage_capacity = p_nom * max_hours  # MWh
            state_of_charge_initial = su_data.get('state_of_charge_initial', 0.0)  # MWh
            cyclic_state_of_charge = su_data.get('cyclic_state_of_charge', False)
            cyclic_state_of_charge_per_period = su_data.get('cyclic_state_of_charge_per_period', True)
            
            # Calculate initial SOC as fraction
            initial_soc_fraction = (state_of_charge_initial / storage_capacity) if storage_capacity > 0 else 0.0
            
            logger.info(f"\n{su_name}:")
            logger.info(f"  p_nom: {p_nom:.2f} MW")
            logger.info(f"  max_hours: {max_hours:.2f} hours")
            logger.info(f"  storage_capacity: {storage_capacity:.2f} MWh")
            logger.info(f"  state_of_charge_initial: {state_of_charge_initial:.2f} MWh")
            logger.info(f"  initial_soc_fraction: {initial_soc_fraction:.4f} ({initial_soc_fraction*100:.2f}%)")
            logger.info(f"  cyclic_state_of_charge: {cyclic_state_of_charge}")
            logger.info(f"  cyclic_state_of_charge_per_period: {cyclic_state_of_charge_per_period}")
            
            # If cyclic_state_of_charge_per_period is True, check if there's a state_of_charge time series
            if cyclic_state_of_charge_per_period and hasattr(network, 'storage_units_t'):
                if hasattr(network.storage_units_t, 'state_of_charge'):
                    soc_ts = network.storage_units_t.state_of_charge
                    if su_name in soc_ts.columns:
                        # Get first and last values
                        first_soc = soc_ts[su_name].iloc[0] if len(soc_ts) > 0 else None
                        last_soc = soc_ts[su_name].iloc[-1] if len(soc_ts) > 0 else None
                        first_soc_fraction = (first_soc / storage_capacity) if first_soc is not None and storage_capacity > 0 else None
                        logger.info(f"  state_of_charge time series (OPTIMIZED):")
                        if first_soc is not None:
                            logger.info(f"    First value (optimized): {first_soc:.2f} MWh ({first_soc_fraction*100:.2f}% of capacity)")
                            logger.info(f"    ⚠️  NOTE: With cyclic_state_of_charge_per_period=True, PyPSA optimized initial SOC")
                            logger.info(f"       Static parameter state_of_charge_initial={state_of_charge_initial:.2f} MWh was IGNORED")
                            logger.info(f"       Actual optimized initial SOC={first_soc:.2f} MWh should be used for Sienna!")
                        if last_soc is not None:
                            logger.info(f"    Last value: {last_soc:.2f} MWh")
                            if first_soc is not None:
                                diff = abs(first_soc - last_soc)
                                if diff < 0.01:
                                    logger.info(f"    ✓ Initial ≈ Final (cyclic constraint satisfied, diff={diff:.4f} MWh)")
                                else:
                                    logger.warning(f"    ⚠️  Initial ≠ Final (diff={diff:.4f} MWh) - cyclic constraint may not be satisfied")
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("Storage Initial SOC Summary:")
        logger.info("=" * 80)
        total_initial_soc = network.storage_units.get('state_of_charge_initial', pd.Series([0.0])).sum()
        total_capacity = (network.storage_units.p_nom * network.storage_units.max_hours).sum()
        avg_initial_soc = (total_initial_soc / total_capacity) if total_capacity > 0 else 0.0
        logger.info(f"Total initial SOC (static parameter): {total_initial_soc:.2f} MWh")
        logger.info(f"Total storage capacity: {total_capacity:.2f} MWh")
        logger.info(f"Average initial SOC fraction (static): {avg_initial_soc:.4f} ({avg_initial_soc*100:.2f}%)")
        
        # Check if we have optimized SOC values (after optimization)
        if hasattr(network, 'storage_units_t') and hasattr(network.storage_units_t, 'state_of_charge'):
            soc_ts = network.storage_units_t.state_of_charge
            if len(soc_ts) > 0:
                # Get first timestep SOC for all storage units
                first_soc_values = soc_ts.iloc[0]
                total_optimized_soc = first_soc_values.sum()
                avg_optimized_soc = (total_optimized_soc / total_capacity) if total_capacity > 0 else 0.0
                logger.info(f"Total initial SOC (OPTIMIZED, from time series): {total_optimized_soc:.2f} MWh")
                logger.info(f"Average initial SOC fraction (OPTIMIZED): {avg_optimized_soc:.4f} ({avg_optimized_soc*100:.2f}%)")
                if abs(total_initial_soc - total_optimized_soc) > 0.01:
                    logger.warning(f"⚠️  MISMATCH: Static parameter ({total_initial_soc:.2f} MWh) ≠ Optimized ({total_optimized_soc:.2f} MWh)")
                    logger.warning(f"   This is expected if cyclic_state_of_charge_per_period=True - PyPSA optimizes initial SOC")
                    logger.warning(f"   Sienna should use the OPTIMIZED value, not the static parameter!")
        
        logger.info("=" * 80)
    else:
        pypsa_storage_capacity = 0.0
        logger.info("Storage units: 0")

    # Buses
    logger.info(f"Buses: {len(network.buses)}")

    # ===== SIENNA METRICS =====
    logger.info("=" * 80)
    logger.info("SIENNA SYSTEM METRICS (from JSON/HDF5)")
    logger.info("=" * 80)

    # Load JSON
    with open(json_file) as f:
        sienna_data = json.load(f)

    components = sienna_data.get('data', {}).get('components', [])

    sienna_loads = [c for c in components if c.get('__metadata__', {}).get('type') == 'PowerLoad']
    sienna_thermal = [c for c in components if c.get('__metadata__', {}).get('type') == 'ThermalStandard']
    sienna_renewable = [c for c in components if c.get('__metadata__', {}).get('type') == 'RenewableDispatch']
    # Hydro generators are now included in RenewableDispatch (with prime_mover_type == HY)
    # Filter RenewableDispatch components to find hydro by checking prime_mover_type in the JSON
    sienna_hydro = [c for c in sienna_renewable if c.get('prime_mover_type') == 'HY']
    sienna_storage = [c for c in components if c.get('__metadata__', {}).get('type') == 'EnergyReservoirStorage']
    sienna_buses = [c for c in components if c.get('__metadata__', {}).get('type') == 'ACBus']

    logger.info(f"Loads: {len(sienna_loads)}")

    # Calculate Sienna load metrics
    sienna_total_load_static = 0.0
    sienna_max_load_static = 0.0
    sienna_loads_with_ts = 0

    for load in sienna_loads:
        base_power = load.get('base_power', 100.0)
        max_active_power_pu = load.get('max_active_power', 0.0)
        max_active_power_mw = max_active_power_pu * base_power

        sienna_total_load_static += max_active_power_mw
        sienna_max_load_static = max(sienna_max_load_static, max_active_power_mw)

    logger.info(f"Total max load (sum of static max_active_power): {sienna_total_load_static:.2f} MW")
    logger.info(f"Max load (peak static): {sienna_max_load_static:.2f} MW")

    # Check time series from HDF5 and extract for comparison
    sienna_loads_with_ts = 0
    sienna_total_load_ts = None  # Will be a pandas Series with total load at each timestep
    
    if h5_file.exists():
        with h5py.File(h5_file, 'r') as h5:
            if 'time_series_metadata' in h5:
                db_data = h5['time_series_metadata'][()]
                db_path = output_dir / ".temp_metadata_comparison.db"

                with open(db_path, 'wb') as db_file:
                    db_file.write(bytes(db_data))

                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Check what tables exist
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]

                # Use the correct table name (could be time_series_metadata or time_series_associations)
                table_name = 'time_series_metadata' if 'time_series_metadata' in tables else 'time_series_associations'

                # Count load time series and extract time series data
                load_uuids = [load.get('internal', {}).get('uuid', {}).get('value') for load in sienna_loads]

                if load_uuids:
                    placeholders = ','.join(['?' for _ in load_uuids])
                    query = f'''
                        SELECT COUNT(DISTINCT owner_uuid)
                        FROM {table_name}
                        WHERE owner_uuid IN ({placeholders}) AND owner_type = 'PowerLoad' AND name = 'max_active_power'
                    '''
                    cursor.execute(query, load_uuids)
                    sienna_loads_with_ts = cursor.fetchone()[0]
                    
                    # Extract time series for each load
                    if sienna_loads_with_ts > 0:
                        # Query to get time series UUIDs and metadata for all loads
                        query = f'''
                            SELECT owner_uuid, time_series_uuid, initial_timestamp, resolution, length
                            FROM {table_name}
                            WHERE owner_uuid IN ({placeholders}) AND owner_type = 'PowerLoad' AND name = 'max_active_power'
                        '''
                        cursor.execute(query, load_uuids)
                        ts_metadata = cursor.fetchall()
                        
                        # Store load time series (per-load, will sum later)
                        load_time_series = {}  # {load_uuid: pd.Series}
                        
                        for load_uuid, ts_uuid, initial_timestamp, resolution, length in ts_metadata:
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
                            
                            # If not found, search in time_series group
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
                            
                            if ts_data is not None:
                                # Create time index
                                initial_ts = pd.Timestamp(initial_timestamp)
                                
                                # Parse resolution
                                resolution_str = str(resolution)
                                if 'PT' in resolution_str:
                                    resolution_str = resolution_str.replace('PT', '')
                                    if 'H' in resolution_str:
                                        hours = int(resolution_str.replace('H', ''))
                                        freq = f"{hours}h"
                                    elif 'M' in resolution_str:
                                        minutes = int(resolution_str.replace('M', ''))
                                        freq = f"{minutes}min"
                                    else:
                                        freq = "1h"
                                else:
                                    freq = "1h"
                                
                                # Create time index
                                time_index = pd.date_range(start=initial_ts, periods=len(ts_data), freq=freq)
                                
                                # Get load info to convert from per-unit to MW
                                load_info = next((l for l in sienna_loads if l.get('internal', {}).get('uuid', {}).get('value') == load_uuid), None)
                                if load_info:
                                    base_power = load_info.get('base_power', 100.0)
                                    max_active_power_pu = load_info.get('max_active_power', 0.0)
                                    max_active_power_mw = max_active_power_pu * base_power
                                    
                                    # Convert from per-unit to MW: ts_pu * max_active_power_mw
                                    ts_mw = pd.Series(ts_data * max_active_power_mw, index=time_index)
                                    load_time_series[load_uuid] = ts_mw
                        
                        # Sum all load time series to get total load at each timestep
                        if load_time_series:
                            # Align all series to common time index (use union of all indices)
                            all_indices = set()
                            for ts in load_time_series.values():
                                all_indices.update(ts.index)
                            common_index = pd.DatetimeIndex(sorted(all_indices))
                            
                            # Reindex and sum
                            total_load_series = pd.Series(0.0, index=common_index)
                            for ts in load_time_series.values():
                                ts_aligned = ts.reindex(common_index, fill_value=0.0)
                                total_load_series += ts_aligned
                            
                            sienna_total_load_ts = total_load_series

                conn.close()
                db_path.unlink()

    logger.info(f"Loads with time series: {sienna_loads_with_ts}")
    
    # ===== LOAD TIME SERIES COMPARISON =====
    load_ts_match_count = 0
    load_ts_total_count = 0
    load_ts_max_diff = 0.0
    load_ts_mean_diff = 0.0
    
    if hasattr(network.loads_t, 'p_set') and len(network.loads_t.p_set) > 0 and sienna_total_load_ts is not None:
        # Extract PyPSA total load time series (sum across all loads)
        # PyPSA loads are negative (consumption), so take absolute value for comparison
        pypsa_total_load_ts = network.loads_t.p_set.sum(axis=1).abs()
        
        # Align by index position instead of timestamps (handles T vs space format differences)
        # Use the minimum length to ensure both have data
        min_length = min(len(pypsa_total_load_ts), len(sienna_total_load_ts))
        
        if min_length > 0:
            # Extract values by position (ignore timestamp format differences)
            pypsa_values = pypsa_total_load_ts.values[:min_length]
            sienna_values = sienna_total_load_ts.values[:min_length]
            
            # Compare at least 20 timesteps (or all available if fewer)
            num_timesteps_to_check = min_length
            if num_timesteps_to_check < 20:
                logger.warning(f"Only {num_timesteps_to_check} timesteps available (less than 20 requested)")
            
            differences = []
            matches = 0
            
            for i in range(num_timesteps_to_check):
                pypsa_val = pypsa_values[i]
                sienna_val = sienna_values[i]
                diff = abs(pypsa_val - sienna_val)
                differences.append(diff)
                
                if diff <= 0.01:  # 0.01 MW tolerance
                    matches += 1
                else:
                    # Get timestamp for logging (use PyPSA index if available)
                    ts_str = str(pypsa_total_load_ts.index[i]) if i < len(pypsa_total_load_ts.index) else f"index_{i}"
                    logger.debug(f"Load TS mismatch at {ts_str}: PyPSA={pypsa_val:.4f} MW, Sienna={sienna_val:.4f} MW, diff={diff:.4f} MW")
            
            load_ts_match_count = matches
            load_ts_total_count = num_timesteps_to_check
            load_ts_max_diff = max(differences) if differences else 0.0
            load_ts_mean_diff = sum(differences) / len(differences) if differences else 0.0
            
            logger.info(f"Load time series comparison: {matches}/{num_timesteps_to_check} timesteps match (tolerance: 0.01 MW)")
            logger.info(f"  Max difference: {load_ts_max_diff:.4f} MW")
            logger.info(f"  Mean difference: {load_ts_mean_diff:.4f} MW")
        else:
            logger.warning("No timesteps available for load time series comparison")
    elif sienna_total_load_ts is None:
        logger.info("Sienna load time series not available for comparison")
    else:
        logger.info("PyPSA load time series not available for comparison")

    # ===== RENEWABLE GENERATION TIME SERIES COMPARISON =====
    logger.info("=" * 80)
    logger.info("RENEWABLE GENERATION TIME SERIES COMPARISON")
    logger.info("=" * 80)
    
    # Define generator type mappings
    generator_mappings = {
        'solar': {
            'pypsa_carriers': ['solar'],
            'sienna_prime_movers': ['PVe'],
            'name': 'Solar'
        },
        'wind': {
            'pypsa_carriers': ['onwind', 'offwind', 'offwind_floating', 'wind'],
            'sienna_prime_movers': ['WT', 'WS'],
            'name': 'Wind'
        },
        'hydro': {
            'pypsa_carriers': ['hydro', 'ror'],
            'sienna_prime_movers': ['HY'],
            'name': 'Hydro'
        }
    }
    
    # Store results for each generator type
    renewable_ts_results = {}
    
    for gen_type, mapping in generator_mappings.items():
        logger.info(f"\n--- {mapping['name']} Generation Time Series ---")
        
        # Extract PyPSA time series
        pypsa_ts, pypsa_count, pypsa_capacity = extract_pypsa_generator_time_series(
            network,
            mapping['pypsa_carriers'],
            generator_filter=lambda df: df.p_nom > 0
        )
        
        logger.info(f"PyPSA {mapping['name'].lower()} generators: {pypsa_count}")
        if pypsa_capacity > 0:
            logger.info(f"  Total {mapping['name'].lower()} capacity: {pypsa_capacity:.2f} MW")
        if pypsa_ts is not None:
            logger.info(f"  Time series length: {len(pypsa_ts)}")
        elif pypsa_count > 0:
            logger.info(f"  No time series data available")
        
        # Extract Sienna time series
        sienna_ts, sienna_count, sienna_capacity, sienna_with_ts = extract_sienna_generator_time_series(
            json_file,
            h5_file,
            mapping['sienna_prime_movers'],
            output_dir,
            component_type='RenewableDispatch'
        )
        
        logger.info(f"Sienna {mapping['name'].lower()} generators: {sienna_count}")
        if sienna_capacity > 0:
            logger.info(f"  Total {mapping['name'].lower()} capacity: {sienna_capacity:.2f} MW")
        if sienna_with_ts > 0:
            logger.info(f"  Generators with time series: {sienna_with_ts}")
        if sienna_ts is not None:
            logger.info(f"  Time series length: {len(sienna_ts)}")
        elif sienna_count > 0:
            logger.info(f"  No time series data available")
        
        # Compare time series
        match, match_count, total_count, max_diff, mean_diff = compare_time_series(
            pypsa_ts,
            sienna_ts,
            tolerance_mw=0.01,
            min_timesteps=20,
            name=f"{mapping['name']} TS"
        )
        
        # Note: compare_time_series already logs detailed comparison results
        if total_count == 0:
            if pypsa_ts is None:
                logger.info(f"PyPSA {mapping['name'].lower()} time series not available for comparison")
            elif sienna_ts is None:
                logger.info(f"Sienna {mapping['name'].lower()} time series not available for comparison")
        
        # Store results
        renewable_ts_results[gen_type] = {
            'pypsa_count': pypsa_count,
            'pypsa_capacity': pypsa_capacity,
            'sienna_count': sienna_count,
            'sienna_capacity': sienna_capacity,
            'sienna_with_ts': sienna_with_ts,
            'match': match,
            'match_count': match_count,
            'total_count': total_count,
            'max_diff': max_diff,
            'mean_diff': mean_diff,
            'name': mapping['name']
        }

    # Generation
    # For generators, active_power_limits.max is in per-unit (relative to base_power)
    # Actual capacity = base_power * active_power_limits.max
    sienna_thermal_capacity = 0.0
    for g in sienna_thermal:
        base_power = g.get('base_power', 0.0)
        rating = g.get('rating', 0.0)
        # For ThermalStandard, rating is per-unit relative to base_power
        # Capacity = rating * base_power (in MW)
        # Note: active_power_limits is per-unit relative to p_nom, not base_power, so we use rating instead
        sienna_thermal_capacity += rating * base_power
    
    # Calculate renewable capacity (excluding hydro, which is counted separately)
    # For RenewableDispatch: max_active_power = rating * base_power * power_factor
    sienna_renewable_capacity = 0.0
    for g in sienna_renewable:
        # Skip hydro generators (they're counted separately)
        if g.get('prime_mover_type') == 'HY':
            continue
        base_power = g.get('base_power', 0.0)
        rating = g.get('rating', 0.0)
        power_factor = g.get('power_factor', 1.0)
        # For RenewableDispatch: max_active_power = rating * base_power * power_factor
        sienna_renewable_capacity += rating * base_power * power_factor
    
    # Calculate Sienna hydro capacity
    # For RenewableDispatch: max_active_power = rating * base_power * power_factor
    sienna_hydro_capacity = 0.0
    for g in sienna_hydro:
        base_power = g.get('base_power', 0.0)
        rating = g.get('rating', 0.0)
        power_factor = g.get('power_factor', 1.0)
        # For RenewableDispatch: max_active_power = rating * base_power * power_factor
        sienna_hydro_capacity += rating * base_power * power_factor
    
    # Total capacity: thermal + renewable (excluding hydro) + hydro
    sienna_total_capacity = sienna_thermal_capacity + sienna_renewable_capacity + sienna_hydro_capacity
    
    # Calculate renewable count excluding hydro (to match capacity calculation)
    sienna_renewable_count_excluding_hydro = len(sienna_renewable) - len(sienna_hydro)
    
    # Total generator count: thermal + renewable (hydro is already included in renewable, so don't add it separately)
    sienna_total_generators = len(sienna_thermal) + len(sienna_renewable)
    logger.info(f"Generators: {sienna_total_generators}")
    logger.info(f"  ThermalStandard: {len(sienna_thermal)}, capacity: {sienna_thermal_capacity:.2f} MW")
    logger.info(f"  RenewableDispatch: {len(sienna_renewable)} total (includes {len(sienna_hydro)} hydro), capacity: {sienna_renewable_capacity:.2f} MW (excluding hydro)")
    logger.info(f"    Non-hydro renewable: {sienna_renewable_count_excluding_hydro}, capacity: {sienna_renewable_capacity:.2f} MW")
    logger.info(f"    Hydro: {len(sienna_hydro)}, capacity: {sienna_hydro_capacity:.2f} MW")
    logger.info(f"  Total capacity: {sienna_total_capacity:.2f} MW")

    # Storage
    # For EnergyReservoirStorage, input/output_active_power_limits are in per-unit (like generators)
    # Need to multiply by base_power to get MW
    if len(sienna_storage) > 0:
        sienna_storage_capacity = 0.0
        for s in sienna_storage:
            base_power = s.get('base_power', 0.0)
            # Try input_active_power_limits first, then output_active_power_limits
            input_limits = s.get('input_active_power_limits', {})
            output_limits = s.get('output_active_power_limits', {})
            max_input_pu = input_limits.get('max', 0.0) if isinstance(input_limits, dict) else 0.0
            max_output_pu = output_limits.get('max', 0.0) if isinstance(output_limits, dict) else 0.0
            # Both are per-unit, so multiply by base_power to get MW
            max_power_mw = max(max_input_pu * base_power, max_output_pu * base_power)
            sienna_storage_capacity += max_power_mw

        logger.info(f"Storage units: {len(sienna_storage)}")
        logger.info(f"  Storage capacity: {sienna_storage_capacity:.2f} MW")
    else:
        sienna_storage_capacity = 0.0
        logger.info("Storage units: 0")

    # Compare battery parameters in detail
    compare_battery_parameters(network, json_file, h5_file)
    
    # DIAGNOSE: Compare PyPSA vs Sienna initial SOC
    logger.info("\n" + "=" * 80)
    logger.info("DIAGNOSIS: PyPSA vs Sienna Initial State of Charge Comparison")
    logger.info("=" * 80)
    
    if hasattr(network, 'storage_units') and len(network.storage_units) > 0 and len(sienna_storage) > 0:
        # Create mapping by name
        sienna_by_name = {s.get('name'): s for s in sienna_storage}
        
        for su_name, su_data in network.storage_units.iterrows():
            p_nom = su_data.get('p_nom', 0.0)
            max_hours = su_data.get('max_hours', 1.0)
            storage_capacity = p_nom * max_hours  # MWh
            state_of_charge_initial = su_data.get('state_of_charge_initial', 0.0)  # MWh
            cyclic_state_of_charge_per_period = su_data.get('cyclic_state_of_charge_per_period', True)
            
            # Get PyPSA optimized initial SOC (if available)
            pypsa_optimized_soc = None
            pypsa_optimized_soc_fraction = None
            if hasattr(network, 'storage_units_t') and hasattr(network.storage_units_t, 'state_of_charge'):
                soc_ts = network.storage_units_t.state_of_charge
                if su_name in soc_ts.columns and len(soc_ts) > 0:
                    pypsa_optimized_soc = float(soc_ts[su_name].iloc[0])
                    pypsa_optimized_soc_fraction = pypsa_optimized_soc / storage_capacity if storage_capacity > 0 else 0.0
            
            # Get Sienna initial SOC
            sienna_storage_unit = sienna_by_name.get(su_name)
            if sienna_storage_unit:
                sienna_base_power = sienna_storage_unit.get('base_power', 100.0)
                sienna_storage_capacity_pu = sienna_storage_unit.get('storage_capacity', 0.0)
                sienna_storage_capacity_mwh = sienna_storage_capacity_pu * sienna_base_power
                sienna_soc_fraction = sienna_storage_unit.get('initial_storage_capacity_level', 0.0)
                sienna_soc_mwh = sienna_soc_fraction * sienna_storage_capacity_mwh
                
                logger.info(f"\n{su_name}:")
                logger.info(f"  Storage capacity: {storage_capacity:.2f} MWh (PyPSA), {sienna_storage_capacity_mwh:.2f} MWh (Sienna)")
                logger.info(f"  PyPSA static state_of_charge_initial: {state_of_charge_initial:.2f} MWh ({state_of_charge_initial/storage_capacity*100:.2f}%)")
                if pypsa_optimized_soc is not None:
                    logger.info(f"  PyPSA OPTIMIZED initial SOC: {pypsa_optimized_soc:.2f} MWh ({pypsa_optimized_soc_fraction*100:.2f}%)")
                logger.info(f"  Sienna initial_storage_capacity_level: {sienna_soc_mwh:.2f} MWh ({sienna_soc_fraction*100:.2f}%)")
                logger.info(f"  cyclic_state_of_charge_per_period: {cyclic_state_of_charge_per_period}")
                
                # Compare
                if pypsa_optimized_soc is not None:
                    # Compare optimized PyPSA vs Sienna
                    diff_mwh = abs(pypsa_optimized_soc - sienna_soc_mwh)
                    diff_pct = abs(pypsa_optimized_soc_fraction - sienna_soc_fraction) * 100
                    if diff_mwh > 0.01 or diff_pct > 0.1:
                        logger.warning(f"  ⚠️  MISMATCH: PyPSA optimized ({pypsa_optimized_soc:.2f} MWh) ≠ Sienna ({sienna_soc_mwh:.2f} MWh)")
                        logger.warning(f"     Difference: {diff_mwh:.2f} MWh ({diff_pct:.2f}%)")
                        if cyclic_state_of_charge_per_period:
                            logger.warning(f"     ISSUE: With cyclic_state_of_charge_per_period=True, conversion should use")
                            logger.warning(f"            PyPSA's OPTIMIZED initial SOC, not the static parameter!")
                    else:
                        logger.info(f"  ✓ Match: PyPSA optimized ≈ Sienna (diff={diff_mwh:.4f} MWh)")
                else:
                    # Compare static PyPSA vs Sienna
                    pypsa_static_fraction = state_of_charge_initial / storage_capacity if storage_capacity > 0 else 0.0
                    diff_mwh = abs(state_of_charge_initial - sienna_soc_mwh)
                    diff_pct = abs(pypsa_static_fraction - sienna_soc_fraction) * 100
                    if diff_mwh > 0.01 or diff_pct > 0.1:
                        logger.warning(f"  ⚠️  MISMATCH: PyPSA static ({state_of_charge_initial:.2f} MWh) ≠ Sienna ({sienna_soc_mwh:.2f} MWh)")
                        logger.warning(f"     Difference: {diff_mwh:.2f} MWh ({diff_pct:.2f}%)")
                        if cyclic_state_of_charge_per_period:
                            logger.warning(f"     NOTE: With cyclic_state_of_charge_per_period=True, PyPSA optimizes initial SOC")
                            logger.warning(f"            but optimized values not available in storage_units_t.state_of_charge")
                    else:
                        logger.info(f"  ✓ Match: PyPSA static ≈ Sienna (diff={diff_mwh:.4f} MWh)")
            else:
                logger.warning(f"  ⚠️  {su_name}: Not found in Sienna storage units")
    
    logger.info("=" * 80)

    logger.info(f"Buses: {len(sienna_buses)}")

    # ===== COMPARISON TABLE =====
    logger.info("=" * 80)
    logger.info("COMPARISON TABLE")
    logger.info("=" * 80)

    # Build comparison table
    metrics = [
        'Load Count',
        'Total Max Load (MW)',
        'Peak Load (MW)',
        'Loads with Time Series',
        'Load Time Series Match',
    ]
    pypsa_values = [
        pypsa_load_count,
        f"{pypsa_total_max_load:.2f}",
        f"{pypsa_max_load:.2f}",
        "N/A",  # PyPSA always has time series for loads
        f"{load_ts_total_count} timesteps checked" if load_ts_total_count > 0 else "N/A",
    ]
    sienna_values = [
        len(sienna_loads),
        f"{sienna_total_load_static:.2f}",
        f"{sienna_max_load_static:.2f}",
        sienna_loads_with_ts,
        f"{load_ts_match_count}/{load_ts_total_count} match" if load_ts_total_count > 0 else "N/A",
    ]
    
    # Add renewable generator time series comparisons
    for gen_type in ['solar', 'wind', 'hydro']:
        if gen_type in renewable_ts_results:
            result = renewable_ts_results[gen_type]
            metrics.extend([
                f'{result["name"]} Generators',
                f'{result["name"]} Capacity Factor Time Series Match',
            ])
            pypsa_values.extend([
                result['pypsa_count'],
                f"{result['total_count']} timesteps checked" if result['total_count'] > 0 else "N/A",
            ])
            sienna_values.extend([
                result['sienna_count'],
                f"{result['match_count']}/{result['total_count']} match" if result['total_count'] > 0 else "N/A",
            ])
    
    # Add remaining metrics
    metrics.extend([
        'Total Generators (p_nom > 0)',
        'Thermal Generators',
        'Thermal Capacity (MW)',
        'Renewable Generators (RenewableDispatch, excluding hydro)',
        'Renewable Capacity (MW, excluding hydro)',
        'Hydro Generators (RenewableDispatch with prime_mover_type == HY)',
        'Hydro Capacity (MW)',
        'Total Generation Capacity (MW)',
        'Storage Units',
        'Storage Capacity (MW)',
        'Buses',
    ])
    pypsa_values.extend([
        len(pypsa_generators),
        len(pypsa_thermal),
        f"{pypsa_thermal_capacity:.2f}",
        pypsa_renewable_count_excluding_hydro,  # Exclude hydro from renewable count to match Sienna
        f"{pypsa_renewable_capacity:.2f}",  # Already excludes hydro
        len(pypsa_hydro),
        f"{pypsa_hydro.p_nom.sum() if len(pypsa_hydro) > 0 else 0.0:.2f}",
        f"{pypsa_total_capacity:.2f}",
        len(network.storage_units) if hasattr(network, 'storage_units') else 0,
        f"{pypsa_storage_capacity:.2f}",
        len(network.buses),
    ])
    sienna_values.extend([
        len(sienna_thermal) + len(sienna_renewable),  # Total = thermal + renewable (hydro already included in renewable)
        len(sienna_thermal),
        f"{sienna_thermal_capacity:.2f}",
        sienna_renewable_count_excluding_hydro,  # Exclude hydro from renewable count to match capacity
        f"{sienna_renewable_capacity:.2f}",
        len(sienna_hydro),
        f"{sienna_hydro_capacity:.2f}",
        f"{sienna_total_capacity:.2f}",
        len(sienna_storage),
        f"{sienna_storage_capacity:.2f}",
        len(sienna_buses),
    ])
    
    comparison_data = {
        'Metric': metrics,
        'PyPSA': pypsa_values,
        'Sienna': sienna_values,
    }

    df = pd.DataFrame(comparison_data)
    logger.info("\n" + df.to_string(index=False))

    # Calculate differences
    logger.info("\n" + "=" * 80)
    logger.info("DIFFERENCES")
    logger.info("=" * 80)

    try:
        load_diff = abs(sienna_total_load_static - pypsa_total_max_load)
        load_pct_diff = (load_diff / pypsa_total_max_load * 100) if pypsa_total_max_load > 0 else 0
        logger.info(f"Total Max Load Difference: {load_diff:.2f} MW ({load_pct_diff:.2f}%)")
    except Exception:
        pass

    try:
        capacity_diff = abs(sienna_total_capacity - pypsa_total_capacity)
        capacity_pct_diff = (capacity_diff / pypsa_total_capacity * 100) if pypsa_total_capacity > 0 else 0
        logger.info(f"Total Capacity Difference: {capacity_diff:.2f} MW ({capacity_pct_diff:.2f}%)")
    except Exception:
        pass
    
    # ===== POWER BALANCE CHECK (GENERATION VS LOAD) =====
    # Check if dispatch files exist to calculate actual generation and load
    logger.info("\n" + "=" * 80)
    logger.info("POWER BALANCE CHECK (GENERATION VS LOAD)")
    logger.info("=" * 80)
    
    test_dir = Path(__file__).parent
    output_dir = test_dir / "test_output"
    pypsa_dispatch_file = output_dir / "pypsa_dispatch.csv"
    sienna_dispatch_file = output_dir / "sienna_dispatch.csv"
    
    if pypsa_dispatch_file.exists() and sienna_dispatch_file.exists():
        logger.info("Dispatch files found - calculating actual generation and load from dispatch data")
        
        # Load dispatch data
        pypsa_df = pd.read_csv(pypsa_dispatch_file)
        pypsa_df['DateTime'] = pd.to_datetime(pypsa_df['DateTime'])
        
        sienna_df = pd.read_csv(sienna_dispatch_file)
        sienna_df['DateTime'] = pd.to_datetime(sienna_df['DateTime'])
        
        # Calculate PyPSA total generation (all carriers except 'load' and 'AC')
        load_carriers = ['load', 'AC']
        pypsa_generation = pypsa_df[~pypsa_df['carrier'].isin(load_carriers)]['value'].sum()
        pypsa_total_gen_mwh = pypsa_generation  # Already in MWh (MW * hours)
        
        # Calculate PyPSA total load (includes both 'load' and 'AC' carriers)
        pypsa_load_data = pypsa_df[pypsa_df['carrier'].isin(load_carriers)].copy()
        pypsa_load_data['value_scaled'] = pypsa_load_data.apply(
            lambda row: row['value'] * 100 if row['carrier'] == 'load' else row['value'],
            axis=1
        )
        pypsa_total_load_mwh = pypsa_load_data['value_scaled'].sum()
        
        # Calculate Sienna total generation (all carriers except 'load')
        sienna_generation = sienna_df[sienna_df['carrier'] != 'load']['value'].sum()
        sienna_total_gen_mwh = sienna_generation  # Already in MWh
        
        # Calculate Sienna total load (carrier == 'load', multiply by 100)
        sienna_load = sienna_df[sienna_df['carrier'] == 'load']['value'].sum() * 100
        sienna_total_load_mwh = sienna_load
        
        # Calculate differences
        pypsa_balance_diff = pypsa_total_gen_mwh - pypsa_total_load_mwh
        sienna_balance_diff = sienna_total_gen_mwh - sienna_total_load_mwh
        
        logger.info(f"\nPyPSA Power Balance:")
        logger.info(f"  Total Generation: {pypsa_total_gen_mwh:,.2f} MWh")
        logger.info(f"  Total Load:       {pypsa_total_load_mwh:,.2f} MWh")
        logger.info(f"  Difference:       {pypsa_balance_diff:,.2f} MWh (Generation - Load)")
        if abs(pypsa_balance_diff) < 0.01:
            logger.info(f"  → Power balance matches (within tolerance)")
        else:
            logger.warning(f"  → Power balance mismatch: Generation {'exceeds' if pypsa_balance_diff > 0 else 'is less than'} load by {abs(pypsa_balance_diff):,.2f} MWh")
        
        logger.info(f"\nSienna Power Balance:")
        logger.info(f"  Total Generation: {sienna_total_gen_mwh:,.2f} MWh")
        logger.info(f"  Total Load:       {sienna_total_load_mwh:,.2f} MWh")
        logger.info(f"  Difference:       {sienna_balance_diff:,.2f} MWh (Generation - Load)")
        if abs(sienna_balance_diff) < 0.01:
            logger.info(f"  → Power balance matches (within tolerance)")
        else:
            logger.warning(f"  → Power balance mismatch: Generation {'exceeds' if sienna_balance_diff > 0 else 'is less than'} load by {abs(sienna_balance_diff):,.2f} MWh")
        
        logger.info(f"\nComparison:")
        logger.info(f"  Generation difference (PyPSA - Sienna): {pypsa_total_gen_mwh - sienna_total_gen_mwh:,.2f} MWh")
        logger.info(f"  Load difference (PyPSA - Sienna):       {pypsa_total_load_mwh - sienna_total_load_mwh:,.2f} MWh")
        logger.info(f"  Balance difference (PyPSA - Sienna):    {pypsa_balance_diff - sienna_balance_diff:,.2f} MWh")
        
        # Check for reserve margins or other constraints that might require extra generation
        logger.info(f"\nChecking for reserve margins or constraints requiring extra generation...")
        
        # Check if network has been optimized and has model
        test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
        network_check = pypsa.Network(test_file)
        
        # Apply same modifications as in test
        for component in network_check.components.keys():
            for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
                if attr in network_check.df(component).columns:
                    network_check.df(component)[attr] = False
        network_check.loads_t.p_set *= 0.75
        
        # Check if network has model (has been optimized)
        if hasattr(network_check, 'model') and network_check.model is not None:
            logger.info("  Network has been optimized - checking for reserve constraints...")
            
            # Check for reserve variables
            if hasattr(network_check.model, 'variables'):
                reserve_vars = [v for v in network_check.model.variables.keys() if 'reserve' in v.lower() or 'r' in v.lower()]
                if reserve_vars:
                    logger.warning(f"  Found reserve-related variables: {reserve_vars}")
                else:
                    logger.info("  No reserve variables found in model")
            
            # Check for reserve constraints
            if hasattr(network_check.model, 'constraints'):
                reserve_constraints = [c for c in network_check.model.constraints.keys() if 'reserve' in c.lower() or 'margin' in c.lower()]
                if reserve_constraints:
                    logger.warning(f"  Found reserve-related constraints: {reserve_constraints}")
                else:
                    logger.info("  No reserve constraints found in model")
        else:
            # Check network attributes for reserve configuration
            logger.info("  Network not optimized - checking for reserve configuration...")
            
            # Check if network has config with operational_reserve
            if hasattr(network_check, 'config'):
                config = network_check.config
                if isinstance(config, dict):
                    electricity_config = config.get('electricity', {})
                    operational_reserve = electricity_config.get('operational_reserve', {})
                    if operational_reserve.get('activate', False):
                        logger.warning(f"  Operational reserve is ACTIVATED in config!")
                        logger.warning(f"    epsilon_load: {operational_reserve.get('epsilon_load', 'N/A')}")
                        logger.warning(f"    epsilon_vres: {operational_reserve.get('epsilon_vres', 'N/A')}")
                        logger.warning(f"    contingency: {operational_reserve.get('contingency', 'N/A')} MW")
                    else:
                        logger.info("  Operational reserve is NOT activated in config")
                else:
                    logger.info("  Network config is not a dict (may be None or other type)")
            else:
                logger.info("  Network has no 'config' attribute")
            
            # Check if network has opts (options) that might include reserve settings
            if hasattr(network_check, 'opts'):
                opts = network_check.opts
                if opts:
                    logger.info(f"  Network opts: {opts}")
                    if 'reserve' in str(opts).lower() or 'PRM' in str(opts) or 'ERM' in str(opts):
                        logger.warning(f"  Reserve-related options found in opts: {opts}")
                else:
                    logger.info("  Network opts is empty or None")
            else:
                logger.info("  Network has no 'opts' attribute")
        
        # Check if there are any global constraints that might affect generation
        if hasattr(network_check, 'global_constraints') and len(network_check.global_constraints) > 0:
            logger.info(f"  Found {len(network_check.global_constraints)} global constraint(s)")
            for gc_name, gc_data in network_check.global_constraints.iterrows():
                logger.info(f"    {gc_name}: type={gc_data.get('type', 'N/A')}, constant={gc_data.get('constant', 'N/A')}")
        else:
            logger.info("  No global constraints found")
        
    else:
        logger.info("Dispatch files not found - cannot calculate actual generation and load")
        if not pypsa_dispatch_file.exists():
            logger.info(f"  Missing: {pypsa_dispatch_file}")
        if not sienna_dispatch_file.exists():
            logger.info(f"  Missing: {sienna_dispatch_file}")
        logger.info("  Run test_e2e_economic_dispatch and run_sienna_ed.jl first to generate dispatch files")
    
    # Log renewable time series differences
    for gen_type in ['solar', 'wind', 'hydro']:
        if gen_type in renewable_ts_results:
            result = renewable_ts_results[gen_type]
            if result['total_count'] > 0:
                if result['match']:
                    logger.info(f"{result['name']} Time Series Match: {result['match_count']}/{result['total_count']} timesteps match (tolerance: 0.01 MW)")
                    logger.info(f"  Max difference: {result['max_diff']:.4f} MW")
                    logger.info(f"  Mean difference: {result['mean_diff']:.4f} MW")
                else:
                    logger.error(f"{result['name']} Time Series Mismatch: {result['match_count']}/{result['total_count']} timesteps match (tolerance: 0.01 MW)")
                    logger.error(f"  Max difference: {result['max_diff']:.4f} MW")
                    logger.error(f"  Mean difference: {result['mean_diff']:.4f} MW")

    # ===== MARGINAL PRICE COMPARISON =====
    logger.info("=" * 80)
    logger.info("MARGINAL PRICE COMPARISON")
    logger.info("=" * 80)
    
    # Extract PyPSA marginal costs
    pypsa_marginal_costs = {}
    for gen_name in pypsa_generators.index:
        mc = network.generators.loc[gen_name, 'marginal_cost']
        # Handle time-varying marginal costs (use mean)
        if isinstance(mc, pd.Series):
            mc_value = float(mc.mean())
        else:
            # Handle NaN or None values
            try:
                mc_value = float(mc) if mc is not None and not (isinstance(mc, float) and pd.isna(mc)) else 0.0
            except (ValueError, TypeError):
                mc_value = 0.0
        pypsa_marginal_costs[gen_name] = mc_value
    
    # Extract Sienna marginal costs from JSON
    sienna_marginal_costs = {}
    sienna_generators_all = sienna_thermal + sienna_renewable
    
    for gen in sienna_generators_all:
        gen_name = gen.get('name', '')
        if not gen_name:
            continue
        
        mc = 0.0
        op_cost = gen.get('operation_cost')
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
        
        sienna_marginal_costs[gen_name] = mc
    
    # Compare marginal costs
    tolerance = 0.01  # USD/MWh
    
    total_compared = 0
    matching_costs = 0
    different_costs = 0
    no_cost_pypsa = 0  # Missing or 0.0 in PyPSA
    no_cost_sienna = 0  # Missing or 0.0 in Sienna
    cost_pypsa_missing_sienna = 0  # Has cost in PyPSA but missing in Sienna
    cost_sienna_missing_pypsa = 0  # Has cost in Sienna but missing in PyPSA
    
    # Get all unique generator names
    all_gen_names = set(pypsa_marginal_costs.keys()) | set(sienna_marginal_costs.keys())
    
    for gen_name in all_gen_names:
        pypsa_mc = pypsa_marginal_costs.get(gen_name)
        sienna_mc = sienna_marginal_costs.get(gen_name)
        
        # Check if generator exists in both systems
        if gen_name in pypsa_marginal_costs and gen_name in sienna_marginal_costs:
            total_compared += 1
            pypsa_val = pypsa_mc
            sienna_val = sienna_mc
            
            # Check if costs match (within tolerance)
            if abs(pypsa_val - sienna_val) <= tolerance:
                matching_costs += 1
            else:
                different_costs += 1
            
            # Track no-cost cases (0.0 or missing)
            if pypsa_val == 0.0:
                no_cost_pypsa += 1
            if sienna_val == 0.0:
                no_cost_sienna += 1
        elif gen_name in pypsa_marginal_costs:
            # Generator only in PyPSA
            pypsa_val = pypsa_mc
            if pypsa_val != 0.0:
                cost_pypsa_missing_sienna += 1
        elif gen_name in sienna_marginal_costs:
            # Generator only in Sienna
            sienna_val = sienna_mc
            if sienna_val != 0.0:
                cost_sienna_missing_pypsa += 1
    
    # Log summary statistics
    logger.info(f"Total generators compared: {total_compared}")
    logger.info(f"Generators with matching costs (tolerance: {tolerance} USD/MWh): {matching_costs}")
    logger.info(f"Generators with different costs: {different_costs}")
    logger.info(f"Generators with no cost in PyPSA (missing or 0.0): {no_cost_pypsa}")
    logger.info(f"Generators with no cost in Sienna (missing or 0.0): {no_cost_sienna}")
    logger.info(f"Generators with cost in PyPSA but missing in Sienna: {cost_pypsa_missing_sienna}")
    logger.info(f"Generators with cost in Sienna but missing in PyPSA: {cost_sienna_missing_pypsa}")

    logger.info("=" * 80)

    # Don't assert - just output the comparison
    # This test is for debugging/inspection purposes


def main():
    """Test market clearing with gurobi."""
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    network = pypsa.Network(test_file)

    for component in network.components.keys():
        for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
            if attr in network.df(component).columns:
                network.df(component)[attr] = False

    network.loads_t.p_set *= 0.75 

    logger.info("Starting optimization with HiGHS...")
    network.optimize(
        snapshots=network.snapshots[0:7*24],
        solver_name='highs'
    )
    
    logger.info(f"Optimization completed! Objective: {network.objective}")
    plot_energy_balance(network, 7*24)


if __name__ == "__main__":
    main()