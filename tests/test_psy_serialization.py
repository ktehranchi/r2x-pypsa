from r2x.api import System
from r2x.models import ThermalStandard, RenewableDispatch
from datetime import datetime, timedelta
from infrasys import SingleTimeSeries

from r2x_pypsa.models import PypsaGenerator, PypsaBus
from r2x_pypsa.models.property_values import PypsaProperty
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy


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
