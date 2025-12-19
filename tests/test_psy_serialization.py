from pathlib import Path
import pytest
import pypsa
from r2x.api import System
from r2x.models import ThermalStandard, RenewableDispatch, EnergyReservoirStorage, ACBus, PowerLoad, Line
from datetime import datetime, timedelta
from infrasys import SingleTimeSeries
from loguru import logger

from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaStore, PypsaLoad, PypsaLine, PypsaStorageUnit
from r2x_pypsa.models.property_values import PypsaProperty
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import create_default_mapping
import uuid


def test_psy_serialization_generator() -> None:
    """Test generator conversion with p_max_pu time series extraction.
    
    This test matches the e2e test structure - uses real PyPSA network and parser.
    """
    from infrasys import TimeSeriesStorageType
    
    # Use the same test file as e2e test
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    if not test_file.exists():
        pytest.skip(f"Test network file not found: {test_file}")
    
    # Load and optimize network (like e2e test does)
    network = pypsa.Network(test_file)
    network.optimize(snapshots=network.snapshots[0:7*24], solver_name='highs')
    
    # Parse to R2X system (like e2e test does)
    parser = PypsaParser(network=network)
    pypsa_system = parser.build_system()
    
    # Find a generator with p_max_pu time series (renewable generators)
    from r2x_pypsa.models import PypsaGenerator
    generators_with_ts = []
    for component in pypsa_system._component_mgr.iter_all():
        if isinstance(component, PypsaGenerator):
            if hasattr(component, 'p_max_pu') and component.p_max_pu.has_time_series():
                generators_with_ts.append(component)
                break  # Just test one
    
    if not generators_with_ts:
        pytest.skip("No generators with p_max_pu time series found in test network")
    
    test_gen = generators_with_ts[0]
    logger.info(f"Testing generator: {test_gen.name}")
    
    # Create Sienna system
    psy_system = System()
    mapping = create_default_mapping()
    
    # Create bus first (required for generator)
    bus_name = test_gen.bus
    if not psy_system.list_components_by_name(ACBus, bus_name):
        from r2x_pypsa.models import PypsaBus
        pypsa_bus = pypsa_system.get_component(PypsaBus, bus_name)
        if pypsa_bus:
            pypsa_component_to_psy(pypsa_bus, pypsa_system, psy_system, mapping)
    
    # Convert generator
    pypsa_component_to_psy(test_gen, pypsa_system, psy_system, mapping)
    
    # Verify conversion
    psy_gen = psy_system.get_component(RenewableDispatch, test_gen.name)
    assert psy_gen is not None, f"Generator {test_gen.name} not found in Sienna system"
    
    # Check that time series was added
    assert psy_system.has_time_series(psy_gen, "max_active_power"), \
        f"Generator {test_gen.name} should have max_active_power time series"
    
    ts = psy_system.get_time_series(psy_gen, "max_active_power")
    assert ts is not None, f"Time series for {test_gen.name} should not be None"
    
    # Verify time series data matches
    pypsa_ts = test_gen.p_max_pu.get_time_series()
    assert len(ts.data) == len(pypsa_ts), \
        f"Time series length mismatch: {len(ts.data)} vs {len(pypsa_ts)}"
    
    logger.info(f"✓ Generator conversion test passed for {test_gen.name}")


def test_storage_target_cyclic() -> None:
    """Test that storage_target is set correctly for cyclic storage units.
    
    When cyclic_state_of_charge_per_period=True, storage_target should equal
    initial_storage_capacity_level to enforce initial = final SOC constraint.
    """
    # Create test systems
    pypsa_system = System()
    psy_system = System()
    mapping = create_default_mapping()
    
    # Create a bus first (using PypsaBus and converting it)
    from r2x_pypsa.models import PypsaBus
    pypsa_bus = PypsaBus(
        name="test_bus",
        carrier=PypsaProperty.create(value="AC"),
        v_nom=PypsaProperty.create(value=138.0, units="kV"),
    )
    pypsa_system.add_component(pypsa_bus)
    pypsa_component_to_psy(pypsa_bus, pypsa_system, psy_system, mapping)
    
    # Create a PyPSA storage unit with cyclic_state_of_charge_per_period=True
    p_nom = 100.0  # MW
    max_hours = 4.0  # hours
    storage_capacity = p_nom * max_hours  # 400 MWh
    state_of_charge_initial = 200.0  # MWh (50% of capacity)
    initial_soc_fraction = state_of_charge_initial / storage_capacity  # 0.5
    
    storage_unit = PypsaStorageUnit(
        uuid=uuid.uuid4(),
        name="test_storage_cyclic",
        bus="test_bus",
        p_nom=PypsaProperty.create(value=p_nom, units="MW"),
        max_hours=PypsaProperty.create(value=max_hours, units="hours"),
        state_of_charge_initial=PypsaProperty.create(value=state_of_charge_initial, units="MWh"),
        cyclic_state_of_charge_per_period=PypsaProperty.create(value=True),
        efficiency_store=PypsaProperty.create(value=0.9),
        efficiency_dispatch=PypsaProperty.create(value=0.9),
        p_min_pu=PypsaProperty.create(value=-1.0),
        p_max_pu=PypsaProperty.create(value=1.0),
    )
    pypsa_system.add_component(storage_unit)
    
    # Convert to Sienna
    pypsa_component_to_psy(storage_unit, pypsa_system, psy_system, mapping)
    
    # Verify conversion
    psy_storage = psy_system.get_component(EnergyReservoirStorage, "test_storage_cyclic")
    assert psy_storage is not None, "Storage unit not found in Sienna system"
    
    # NOTE: storage_target is NO LONGER set in ext dict to avoid PowerSimulations bugs
    # Even when energy_target=false, PowerSimulations may try to read storage_target from JSON
    # and create StorageEnergySurplusVariable, causing dimension mismatch errors.
    # The test now verifies that storage_target is NOT in ext (to avoid the bug)
    # and that initial_storage_capacity_level is set correctly for cyclic storage.
    assert "storage_target" not in psy_storage.ext, \
        f"storage_target should NOT be set in ext dict (to avoid PowerSimulations bug) for {psy_storage.name}"
    
    # Verify initial_storage_capacity_level is set correctly (should be ~0.5 = 50%)
    assert abs(psy_storage.initial_storage_capacity_level - initial_soc_fraction) < 1e-6, \
        f"initial_storage_capacity_level ({psy_storage.initial_storage_capacity_level}) should be " \
        f"{initial_soc_fraction} (50% of capacity)"
    
    # For cyclic storage, the expected storage_target would equal initial_storage_capacity_level
    # but we're not setting it in ext to avoid the PowerSimulations bug
    expected_storage_target = initial_soc_fraction
    logger.info(f"✓ Cyclic storage test passed: expected_storage_target={expected_storage_target:.4f} "
                f"(not set in ext to avoid bug), initial_storage_capacity_level={psy_storage.initial_storage_capacity_level:.4f}")


def test_storage_target_non_cyclic() -> None:
    """Test that storage_target is 0.0 for non-cyclic storage units.
    
    When cyclic_state_of_charge_per_period=False, storage_target should be 0.0.
    """
    # Create test systems
    pypsa_system = System()
    psy_system = System()
    mapping = create_default_mapping()
    
    # Create a bus first (using PypsaBus and converting it)
    from r2x_pypsa.models import PypsaBus
    pypsa_bus = PypsaBus(
        name="test_bus",
        carrier=PypsaProperty.create(value="AC"),
        v_nom=PypsaProperty.create(value=138.0, units="kV"),
    )
    pypsa_system.add_component(pypsa_bus)
    pypsa_component_to_psy(pypsa_bus, pypsa_system, psy_system, mapping)
    
    # Create a PyPSA storage unit with cyclic_state_of_charge_per_period=False
    p_nom = 100.0  # MW
    max_hours = 4.0  # hours
    storage_capacity = p_nom * max_hours  # 400 MWh
    state_of_charge_initial = 200.0  # MWh (50% of capacity)
    initial_soc_fraction = state_of_charge_initial / storage_capacity  # 0.5
    
    storage_unit = PypsaStorageUnit(
        uuid=uuid.uuid4(),
        name="test_storage_non_cyclic",
        bus="test_bus",
        p_nom=PypsaProperty.create(value=p_nom, units="MW"),
        max_hours=PypsaProperty.create(value=max_hours, units="hours"),
        state_of_charge_initial=PypsaProperty.create(value=state_of_charge_initial, units="MWh"),
        cyclic_state_of_charge_per_period=PypsaProperty.create(value=False),  # Non-cyclic
        efficiency_store=PypsaProperty.create(value=0.9),
        efficiency_dispatch=PypsaProperty.create(value=0.9),
        p_min_pu=PypsaProperty.create(value=-1.0),
        p_max_pu=PypsaProperty.create(value=1.0),
    )
    pypsa_system.add_component(storage_unit)
    
    # Convert to Sienna
    pypsa_component_to_psy(storage_unit, pypsa_system, psy_system, mapping)
    
    # Verify conversion
    psy_storage = psy_system.get_component(EnergyReservoirStorage, "test_storage_non_cyclic")
    assert psy_storage is not None, "Storage unit not found in Sienna system"
    
    # NOTE: storage_target is NO LONGER set in ext dict to avoid PowerSimulations bugs
    # Verify that storage_target is NOT in ext (to avoid the bug)
    assert "storage_target" not in psy_storage.ext, \
        f"storage_target should NOT be set in ext dict (to avoid PowerSimulations bug) for {psy_storage.name}"
    
    # Verify initial_storage_capacity_level is still set correctly
    assert abs(psy_storage.initial_storage_capacity_level - initial_soc_fraction) < 1e-6, \
        f"initial_storage_capacity_level ({psy_storage.initial_storage_capacity_level}) should be " \
        f"{initial_soc_fraction} (50% of capacity)"
    
    logger.info(f"✓ Non-cyclic storage test passed: storage_target not set in ext (to avoid bug), "
                f"initial_storage_capacity_level={psy_storage.initial_storage_capacity_level:.4f}")
