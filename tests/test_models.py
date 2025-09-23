import pytest
from r2x_pypsa.parser import PypsaGenerator


def test_pypsa_generator():
    """Test PypsaGenerator model creation and properties."""
    generator = PypsaGenerator(
        name="test_gen",
        bus="bus1",
        carrier="solar",
        p_nom=100.0,
        marginal_cost=25.0
    )
    
    assert isinstance(generator, PypsaGenerator)
    assert generator.name == "test_gen"
    assert generator.bus == "bus1"
    assert generator.carrier == "solar"
    assert generator.p_nom == 100.0
    assert generator.marginal_cost == 25.0
    assert generator.uuid is not None


def test_pypsa_generator_defaults():
    """Test PypsaGenerator with default values."""
    generator = PypsaGenerator(
        name="test_gen",
        bus="bus1",
        carrier="solar"
    )
    
    assert generator.p_nom == 0.0
    assert generator.p_nom_extendable is False
    assert generator.marginal_cost == 0.0
    assert generator.capital_cost == 0.0
    assert generator.efficiency == 1.0
    assert generator.p_max_pu == 1.0
    assert generator.p_min_pu == 0.0
    assert generator.uuid is not None


def test_pypsa_generator_uuid_generation():
    """Test that UUID is auto-generated when not provided."""
    gen1 = PypsaGenerator(name="gen1", bus="bus1", carrier="solar")
    gen2 = PypsaGenerator(name="gen2", bus="bus1", carrier="wind")
    
    assert gen1.uuid != gen2.uuid
    assert len(gen1.uuid) > 0
    assert len(gen2.uuid) > 0
