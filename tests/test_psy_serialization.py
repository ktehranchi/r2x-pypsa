from pathlib import Path
import pytest
import pypsa
from r2x.api import System
from r2x.models import ThermalStandard, RenewableDispatch, EnergyReservoirStorage, ACBus, PowerLoad, Line
from datetime import datetime, timedelta
from infrasys import SingleTimeSeries
from loguru import logger

from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaStore, PypsaLoad, PypsaLine
from r2x_pypsa.models.property_values import PypsaProperty
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import create_default_mapping


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
    
    # Convert to PSY system (like e2e test does)
    mapping = create_default_mapping()
    psy_system = System(
        name="PSY system",
        auto_add_composed_components=True,
        time_series_storage_type=TimeSeriesStorageType.HDF5
    )
    
    # Convert all components (like e2e test does)
    for component in pypsa_system._component_mgr.iter_all():
        try:
            pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
        except Exception as e:
            logger.warning(f"Failed to convert component {component.name}: {e}")
            continue
    
    # Check generator was converted
    psy_generators = list(psy_system.get_components(RenewableDispatch)) + list(psy_system.get_components(ThermalStandard))
    assert len(psy_generators) > 0, "Should have generators"
    
    # Find our test generator
    psy_gen = None
    for gen in psy_generators:
        if gen.name == test_gen.name:
            psy_gen = gen
            break
    
    assert psy_gen is not None, f"Generator {test_gen.name} should be converted"
    
    # Check that time series was extracted and added
    time_series_list = list(psy_system.list_time_series(psy_gen))
    assert len(time_series_list) > 0, f"Generator {test_gen.name} should have time series"
    
    # Find the max_active_power time series
    max_power_ts = None
    for ts in time_series_list:
        if ts.name == "max_active_power":
            max_power_ts = ts
            break
    
    assert max_power_ts is not None, f"Generator {test_gen.name} should have max_active_power time series"
    # Check it has data (length depends on optimization snapshots)
    assert len(max_power_ts.data) > 0, "Time series should have data"
    assert max_power_ts.resolution == timedelta(hours=1), "Resolution should be 1 hour"


def test_psy_serialization_store() -> None:
    """Test PypsaStore to EnergyReservoirStorage conversion."""
    system = System()
    
    # Create a PypsaStore
    store = PypsaStore(
        name="test_store",
        bus="Bus1",
        e_nom=PypsaProperty.create(value=100.0, units="MWh"),
        marginal_cost=PypsaProperty.create(value=50.0, units="usd/MWh"),
        standing_loss=PypsaProperty.create(value=0.01),  # 1% standing loss
        carrier=PypsaProperty.create(value="hydrogen")
    )
    
    # Create a bus
    bus = PypsaBus(name="Bus1")
    
    system.add_components(store, bus)
    
    psy_system = System()
    # Convert the bus first
    pypsa_component_to_psy(bus, system, psy_system)
    # Then convert the store
    pypsa_component_to_psy(store, system, psy_system)
    
    # Check that the store was converted
    psy_stores = list(psy_system.get_components(EnergyReservoirStorage))
    assert len(psy_stores) == 1
    assert psy_stores[0].name == store.name
    assert psy_stores[0].storage_capacity.magnitude == 100.0
    assert psy_stores[0].efficiency.input == 0.99  # 1 - 0.01 standing loss
    assert psy_stores[0].efficiency.output == 0.99  # 1 - 0.01 standing loss


def test_psy_serialization_from_netcdf() -> None:
    """Test PyPSA to PSY conversion using the test_network.nc file."""
    test_file = Path(__file__).parent / "data" / "test_network.nc"
    if not test_file.exists():
        pytest.skip(f"Test network file not found: {test_file}")
    
    # Parse and convert
    parser = PypsaParser(netcdf_file=str(test_file))
    pypsa_system = parser.build_system()
    psy_system = System()
    
    # Convert all components
    for component in pypsa_system._component_mgr.iter_all():
        pypsa_component_to_psy(component, pypsa_system, psy_system)
    
    # Basic validation
    psy_buses = list(psy_system.get_components(ACBus))
    psy_generators = list(psy_system.get_components(ThermalStandard)) + list(psy_system.get_components(RenewableDispatch))
    
    assert len(psy_buses) > 0, "Should have buses"
    assert len(psy_generators) > 0, "Should have generators"
    
    # Compare lengths - should have same number of buses
    pypsa_buses = list(pypsa_system.get_components(PypsaBus))
    assert len(psy_buses) == len(pypsa_buses), f"Expected {len(pypsa_buses)} buses, got {len(psy_buses)}"
