import pytest
from r2x_pypsa.models import PypsaGenerator
from r2x_pypsa.models.property_values import PypsaProperty


def test_pypsa_generator():
    """Test PypsaGenerator model creation and properties."""
    
    generator = PypsaGenerator(
        name="test_gen",
        bus="bus1",
        carrier=PypsaProperty.create(value="solar"),
        p_nom=PypsaProperty.create(value=100.0, units="MW"),
        marginal_cost=PypsaProperty.create(value=25.0, units="usd/MWh")
    )
    
    assert isinstance(generator, PypsaGenerator)
    assert generator.name == "test_gen"
    assert generator.bus == "bus1"
    assert generator.carrier.get_value() == "solar"
    assert generator.p_nom.get_value() == 100.0
    assert generator.marginal_cost.get_value() == 25.0
    assert generator.uuid is not None


def test_pypsa_generator_defaults():
    """Test PypsaGenerator with default values."""
    
    generator = PypsaGenerator(
        name="test_gen",
        bus="bus1",
        carrier=PypsaProperty.create(value="solar")
    )
    
    assert generator.p_nom.get_value() == 0.0
    assert generator.p_nom_extendable.get_value() is False
    assert generator.marginal_cost.get_value() == 0.0
    assert generator.capital_cost.get_value() == 0.0
    assert generator.efficiency.get_value() == 1.0
    assert generator.p_max_pu.get_value() == 1.0
    assert generator.p_min_pu.get_value() == 0.0
    assert generator.uuid is not None


def test_pypsa_generator_uuid_generation():
    """Test that UUID is auto-generated when not provided."""
    
    gen1 = PypsaGenerator(name="gen1", bus="bus1", carrier=PypsaProperty.create(value="solar"))
    gen2 = PypsaGenerator(name="gen2", bus="bus1", carrier=PypsaProperty.create(value="wind"))
    
    assert gen1.uuid != gen2.uuid
    assert str(gen1.uuid) != ""
    assert str(gen2.uuid) != ""
