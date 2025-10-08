from pathlib import Path
import pytest
from r2x.api import System
from r2x.models import ThermalStandard, RenewableDispatch, EnergyReservoirStorage, ACBus, PowerLoad, Line
from datetime import datetime, timedelta
from infrasys import SingleTimeSeries

from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaStore, PypsaLoad, PypsaLine
from r2x_pypsa.models.property_values import PypsaProperty
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.parser import PypsaParser


def test_psy_serialization_generator() -> None:
    # First try a generator with thermal carrier
    system = System()
    gen: PypsaGenerator = PypsaGenerator.example()
    gen.carrier = PypsaProperty.create(value="coal")
    bus: PypsaBus = PypsaBus(name="Bus1")

    initial_time = datetime(year=2012, month=1, day=1)
    ts = SingleTimeSeries.from_array(
        data=range(0, 8760),
        name="p_set",
        initial_timestamp=initial_time,
        resolution=timedelta(hours=1),
    )
    system.add_time_series(ts, gen)
    system.add_components(gen, bus)
    
    psy_system = System()
    # Convert the bus first
    pypsa_component_to_psy(bus, system, psy_system)
    # Then convert the generator
    pypsa_component_to_psy(gen, system, psy_system)
    psy_generators = list(psy_system.get_components(ThermalStandard))
    assert len(psy_generators) == 1
    assert psy_generators[0].name == gen.name

    # Test that if there is no bus we skip it.
    gen2: PypsaGenerator = PypsaGenerator.example()
    gen2.carrier = PypsaProperty.create(value="solar")
    system.add_components(gen2)
    
    psy_system2 = System()
    pypsa_component_to_psy(gen2, system, psy_system2)
    psy_generators2 = list(psy_system2.get_components(ThermalStandard)) + list(psy_system2.get_components(RenewableDispatch))
    assert len(psy_generators2) == 0


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
    """Test PyPSA to PSY conversion using the test_simple_network.nc file."""
    test_file = Path(__file__).parent / "data" / "test_simple_network.nc"
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
