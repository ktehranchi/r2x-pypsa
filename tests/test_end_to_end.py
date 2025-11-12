import pytest
import pypsa
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
    plot_capacity_comparison
)


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
    """Test end-to-end conversion from PyPSA to PSY system."""
    # Use the test data
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    network = pypsa.Network(test_file)

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

    network.optimize(
        snapshots=network.snapshots[0:7*24],
        solver_name='gurobi'
    )

    # Verify optimization completed successfully
    assert network.objective is not None
    logger.info(f"Optimization completed with gurobi, objective: {network.objective}")
    
    # Solver-specific objective value checks
    assert network.objective < 4.23e7
    assert network.objective > 4.21e7

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
    output_file = output_dir / "elec_s380_c7a_ec_lv1_output_optimized.json"
    infrasys_to_psy(psy_system, filename=output_file)
    
    # Verify the output file was created
    assert output_file.exists()
    
    # Note: Not cleaning up output files - they remain in test_output/ for inspection
    
    # Log conversion statistics
    total_components = len(list(pypsa_system._component_mgr.iter_all()))
    successful_conversions = total_components - conversion_failures
    logger.info(f"Converted {successful_conversions}/{total_components} components successfully")


def test_pypsa_sienna_objective_match():
    """Validate that PyPSA and Sienna produce the same objective value."""
    import subprocess
    
    # Run PyPSA optimization (same as test_e2e_economic_dispatch)
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    network = pypsa.Network(test_file)
    
    # Apply modifications
    for component in network.components.keys():
        for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
            if attr in network.df(component).columns:
                network.df(component)[attr] = False
    
    network.loads_t.p_set *= 0.75
    
    # Optimize with PyPSA
    network.optimize(
        snapshots=network.snapshots[0:7*24],
        solver_name='gurobi'
    )
    
    pypsa_objective = network.objective
    logger.info(f"PyPSA objective: ${pypsa_objective:,.2f}")
    
    # Convert to Sienna JSON (already done in test_e2e_economic_dispatch, so use existing file)
    test_dir = Path(__file__).parent
    json_file = test_dir / "test_output" / "elec_s380_c7a_ec_lv1_output_optimized.json"
    
    logger.info(f"Looking for JSON at: {json_file}")
    logger.info(f"JSON exists: {json_file.exists()}")
    
    if not json_file.exists():
        # List what files are in test_output
        output_dir = test_dir / "test_output"
        if output_dir.exists():
            logger.info(f"Files in test_output: {list(output_dir.glob('*'))}")
        raise FileNotFoundError(f"JSON not found at {json_file}. Run test_e2e_economic_dispatch first")
    
    # Run Sienna ED via Julia
    output_file = test_dir / "test_output" / "sienna_objective.txt"
    julia_script = test_dir / "run_sienna_ed.jl"
    
    logger.info(f"Julia script: {julia_script} (exists: {julia_script.exists()})")
    
    if not julia_script.exists():
        raise FileNotFoundError(f"Julia script not found at {julia_script}")
    
    result = subprocess.run(
        ["julia", str(julia_script), str(json_file), str(output_file)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        logger.error(f"Julia script failed: {result.stderr}")
        logger.error(f"Julia stdout: {result.stdout}")
        raise RuntimeError(f"Sienna optimization failed: {result.stderr}")
    
    # Read Sienna objective
    with open(output_file) as f:
        sienna_objective = float(f.read().strip())
    
    logger.info(f"Sienna objective: ${sienna_objective:,.2f}")
    
    # Compare
    diff = abs(sienna_objective - pypsa_objective)
    pct_diff = (diff / pypsa_objective) * 100
    
    logger.info(f"Difference: ${diff:,.2f} ({pct_diff:.2f}%)")
    
    # Assert objectives match within 5%
    assert pct_diff < 5.0, f"Objectives differ by {pct_diff:.2f}% (>${diff:,.2f})"
    logger.info("✓ Objectives match!")


def test_compare_pypsa_sienna_systems():
    """Compare PyPSA and Sienna systems without running optimization."""
    import pandas as pd
    import json
    import h5py
    import sqlite3
    
    # Load PyPSA network
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
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
    
    # Serialize to Sienna format
    test_dir = Path(__file__).parent
    output_dir = test_dir / "test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_file = output_dir / "elec_s380_c7a_ec_lv1_comparison.json"
    # HDF5 filename should match JSON filename (without extension)
    h5_file = output_dir / f"{json_file.stem}.h5"
    
    # Remove old files
    if json_file.exists():
        json_file.unlink()
    if h5_file.exists():
        h5_file.unlink()
    
    infrasys_to_psy(psy_system, filename=json_file)
    
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
    pypsa_generators = network.generators
    pypsa_thermal = network.generators[network.generators.carrier.isin(['coal', 'gas', 'oil', 'nuclear', 'biomass'])]
    pypsa_renewable = network.generators[network.generators.carrier.isin(['solar', 'wind', 'hydro', 'ror'])]
    
    pypsa_thermal_capacity = pypsa_thermal.p_nom.sum() if len(pypsa_thermal) > 0 else 0.0
    pypsa_renewable_capacity = pypsa_renewable.p_nom.sum() if len(pypsa_renewable) > 0 else 0.0
    pypsa_total_capacity = pypsa_generators.p_nom.sum()
    
    logger.info(f"Generators: {len(pypsa_generators)}")
    logger.info(f"  Thermal capacity: {pypsa_thermal_capacity:.2f} MW")
    logger.info(f"  Renewable capacity: {pypsa_renewable_capacity:.2f} MW")
    logger.info(f"  Total capacity: {pypsa_total_capacity:.2f} MW")
    
    # Storage
    if hasattr(network, 'storage_units') and len(network.storage_units) > 0:
        pypsa_storage_capacity = network.storage_units.p_nom.sum()
        logger.info(f"Storage units: {len(network.storage_units)}")
        logger.info(f"  Storage capacity: {pypsa_storage_capacity:.2f} MW")
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
    
    # Check time series from HDF5
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
                
                # Count load time series
                load_uuids = [load.get('internal', {}).get('uuid', {}).get('value') for load in sienna_loads]
                if load_uuids:
                    placeholders = ','.join(['?' for _ in load_uuids])
                    query = f'''
                        SELECT COUNT(DISTINCT owner_uuid)
                        FROM {table_name}
                        WHERE owner_uuid IN ({placeholders}) AND owner_type = 'PowerLoad' AND name = 'active_power'
                    '''
                    cursor.execute(query, load_uuids)
                    sienna_loads_with_ts = cursor.fetchone()[0]
                
                conn.close()
                db_path.unlink()
    
    logger.info(f"Loads with time series: {sienna_loads_with_ts}")
    
    # Generation
    # For generators, max_active_power is in per-unit, multiply by base_power to get MW
    sienna_thermal_capacity = 0.0
    for g in sienna_thermal:
        base_power = g.get('base_power', 100.0)
        max_active_power_pu = g.get('max_active_power', 0.0)
        # max_active_power is per-unit, so multiply by base_power
        sienna_thermal_capacity += max_active_power_pu * base_power
    
    sienna_renewable_capacity = 0.0
    for g in sienna_renewable:
        base_power = g.get('base_power', 100.0)
        max_active_power_pu = g.get('max_active_power', 0.0)
        # max_active_power is per-unit, so multiply by base_power
        sienna_renewable_capacity += max_active_power_pu * base_power
    
    sienna_total_capacity = sienna_thermal_capacity + sienna_renewable_capacity
    
    logger.info(f"Generators: {len(sienna_thermal) + len(sienna_renewable)}")
    logger.info(f"  ThermalStandard: {len(sienna_thermal)}, capacity: {sienna_thermal_capacity:.2f} MW")
    logger.info(f"  RenewableDispatch: {len(sienna_renewable)}, capacity: {sienna_renewable_capacity:.2f} MW")
    logger.info(f"  Total capacity: {sienna_total_capacity:.2f} MW")
    
    # Storage
    # For EnergyReservoirStorage, check both input and output power limits
    if len(sienna_storage) > 0:
        sienna_storage_capacity = 0.0
        for s in sienna_storage:
            base_power = s.get('base_power', 100.0)
            # Try input_active_power_limits first, then output_active_power_limits
            input_limits = s.get('input_active_power_limits', {})
            output_limits = s.get('output_active_power_limits', {})
            max_input_pu = input_limits.get('max', 0.0) if isinstance(input_limits, dict) else 0.0
            max_output_pu = output_limits.get('max', 0.0) if isinstance(output_limits, dict) else 0.0
            # Use the maximum of input or output (both are per-unit)
            max_power_pu = max(max_input_pu, max_output_pu)
            sienna_storage_capacity += max_power_pu * base_power
        logger.info(f"Storage units: {len(sienna_storage)}")
        logger.info(f"  Storage capacity: {sienna_storage_capacity:.2f} MW")
    else:
        sienna_storage_capacity = 0.0
        logger.info("Storage units: 0")
    
    logger.info(f"Buses: {len(sienna_buses)}")
    
    # ===== COMPARISON TABLE =====
    logger.info("=" * 80)
    logger.info("COMPARISON TABLE")
    logger.info("=" * 80)
    
    comparison_data = {
        'Metric': [
            'Load Count',
            'Total Max Load (MW)',
            'Peak Load (MW)',
            'Loads with Time Series',
            'Thermal Generators',
            'Thermal Capacity (MW)',
            'Renewable Generators',
            'Renewable Capacity (MW)',
            'Total Generation Capacity (MW)',
            'Storage Units',
            'Storage Capacity (MW)',
            'Buses',
        ],
        'PyPSA': [
            pypsa_load_count,
            f"{pypsa_total_max_load:.2f}",
            f"{pypsa_max_load:.2f}",
            "N/A",  # PyPSA always has time series for loads
            len(pypsa_thermal),
            f"{pypsa_thermal_capacity:.2f}",
            len(pypsa_renewable),
            f"{pypsa_renewable_capacity:.2f}",
            f"{pypsa_total_capacity:.2f}",
            len(network.storage_units) if hasattr(network, 'storage_units') else 0,
            f"{pypsa_storage_capacity:.2f}",
            len(network.buses),
        ],
        'Sienna': [
            len(sienna_loads),
            f"{sienna_total_load_static:.2f}",
            f"{sienna_max_load_static:.2f}",
            sienna_loads_with_ts,
            len(sienna_thermal),
            f"{sienna_thermal_capacity:.2f}",
            len(sienna_renewable),
            f"{sienna_renewable_capacity:.2f}",
            f"{sienna_total_capacity:.2f}",
            len(sienna_storage),
            f"{sienna_storage_capacity:.2f}",
            len(sienna_buses),
        ],
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
    except:
        pass
    
    try:
        capacity_diff = abs(sienna_total_capacity - pypsa_total_capacity)
        capacity_pct_diff = (capacity_diff / pypsa_total_capacity * 100) if pypsa_total_capacity > 0 else 0
        logger.info(f"Total Capacity Difference: {capacity_diff:.2f} MW ({capacity_pct_diff:.2f}%)")
    except:
        pass
    
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

    logger.info("Starting optimization with Gurobi...")
    network.optimize(
        snapshots=network.snapshots[0:7*24],
        solver_name='gurobi'
    )
    
    logger.info(f"Optimization completed! Objective: {network.objective}")
    plot_energy_balance(network, 7*24)


if __name__ == "__main__":
    main()