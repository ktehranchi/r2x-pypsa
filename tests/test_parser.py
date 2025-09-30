import pytest
import pypsa
import pandas as pd
import logging
from pathlib import Path
from r2x.api import System

from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.models import PypsaGenerator

# Set up logging
logger = logging.getLogger(__name__)


@pytest.fixture
def simple_netcdf_file(tmp_path):
    """Create a simple PyPSA network for testing."""
    # Create a minimal PyPSA network
    n = pypsa.Network()
    
    # Add snapshots
    n.snapshots = pd.date_range("2023-01-01", periods=24, freq="h")
    
    # Add buses
    n.add("Bus", "bus1", carrier="AC", v_nom=138)
    n.add("Bus", "bus2", carrier="AC", v_nom=138)
    
    # Add generators
    n.add("Generator", "gen1", bus="bus1", carrier="solar", p_nom=100, marginal_cost=0)
    n.add("Generator", "gen2", bus="bus1", carrier="wind", p_nom=50, marginal_cost=10)
    n.add("Generator", "gen3", bus="bus2", carrier="gas", p_nom=200, marginal_cost=50)
    
    # Save to temporary NetCDF file
    netcdf_path = tmp_path / "test_network.nc"
    n.export_to_netcdf(netcdf_path)
    
    return str(netcdf_path)


def test_parser_instance(simple_netcdf_file: str) -> None:
    """Test that parser can be instantiated."""
    parser = PypsaParser(netcdf_file=simple_netcdf_file)
    assert isinstance(parser, PypsaParser)


@pytest.fixture
def simple_parser(simple_netcdf_file: str) -> PypsaParser:
    """Create a parser instance for testing."""
    return PypsaParser(netcdf_file=simple_netcdf_file)


def test_build_system(simple_parser: PypsaParser) -> None:
    """Test that the parser can build an R2X system from PyPSA network."""
    parser = simple_parser
    
    system = parser.build_system()
    assert system
    assert isinstance(system, System)
    assert parser.network
    assert isinstance(parser.network, pypsa.Network)
    
    # Check that we have the expected number of generators
    generators = list(system.get_components(PypsaGenerator))
    assert len(generators) == 3  # 3 generators in test network
    
    # Verify generator properties
    gen_names = [gen.name for gen in generators]
    assert "gen1" in gen_names
    assert "gen2" in gen_names
    assert "gen3" in gen_names
    
    # Check specific generator properties
    gen1 = next(gen for gen in generators if gen.name == "gen1")
    assert gen1.bus == "bus1"
    assert gen1.carrier == "solar"
    assert gen1.p_nom == 100.0
    # marginal_cost may be static (float) or a Series; both acceptable
    if isinstance(gen1.marginal_cost, pd.Series):
        assert all(gen1.marginal_cost == 0.0)
    else:
        assert gen1.marginal_cost == 0.0


def test_generator_attributes(simple_parser: PypsaParser) -> None:
    """Test that generator attributes are correctly extracted."""
    parser = simple_parser
    system = parser.build_system()
    
    generators = list(system.get_components(PypsaGenerator))
    
    # Test that all generators have required attributes
    for gen in generators:
        assert hasattr(gen, 'name')
        assert hasattr(gen, 'bus')
        assert hasattr(gen, 'carrier')
        assert hasattr(gen, 'p_nom')
        assert hasattr(gen, 'marginal_cost')
        assert hasattr(gen, 'uuid')
        assert gen.uuid is not None  # UUID should be auto-generated
        # Time-varying attributes may be float (static) or Series (TS)
        assert isinstance(gen.marginal_cost, (float, pd.Series))
        assert isinstance(gen.efficiency, (float, pd.Series))
        assert isinstance(gen.p_max_pu, (float, pd.Series))
        assert isinstance(gen.p_min_pu, (float, pd.Series))


def test_real_pypsa_file():
    """Test parser with real PyPSA network file."""
    # Use the real PyPSA file from tests/data (we can change this file later)
    real_netcdf_file = Path(__file__).parent / "data" / "elec_s10_c8_ec_lv1.0_REM-3h_E.nc"
    
    # Verify file exists
    assert real_netcdf_file.exists(), f"Test file not found: {real_netcdf_file}"
    
    # Create parser with real file
    parser = PypsaParser(netcdf_file=str(real_netcdf_file))
    assert isinstance(parser, PypsaParser)
    
    # Build system from real network
    system = parser.build_system()
    assert system
    assert isinstance(system, System)
    assert parser.network
    assert isinstance(parser.network, pypsa.Network)
    
    # Get generators from real network
    generators = list(system.get_components(PypsaGenerator))
    
    # Verify we have generators (real network should have many)
    assert len(generators) == 98, "Network should have 98 generators"
    
    
    # Test that generators have proper attributes
    for gen in generators[:5]:  # Test first 5 generators
        assert hasattr(gen, 'name')
        assert hasattr(gen, 'bus')
        assert hasattr(gen, 'carrier')
        assert hasattr(gen, 'p_nom')
        assert hasattr(gen, 'marginal_cost')
        assert hasattr(gen, 'uuid')
        assert gen.uuid is not None
    
    # Verify we can access the original PyPSA network data
    assert len(parser.network.generators) > 0
    assert len(parser.network.buses) > 0

def test_empty_network(tmp_path):
    """Test parser with empty PyPSA network."""
    # Create empty network
    n = pypsa.Network()
    n.snapshots = pd.date_range("2023-01-01", periods=1, freq="h")
    
    netcdf_path = tmp_path / "empty_network.nc"
    n.export_to_netcdf(netcdf_path)
    
    parser = PypsaParser(netcdf_file=str(netcdf_path))
    system = parser.build_system()
    
    # Should have no generators
    generators = list(system.get_components(PypsaGenerator))
    assert len(generators) == 0


def test_time_varying_data(tmp_path):
    """Test parser with time-varying generator data."""
    # Create network with time-varying data
    n = pypsa.Network()
    n.snapshots = pd.date_range("2023-01-01", periods=4, freq="h")
    
    # Add buses
    n.add("Bus", "bus1", carrier="AC", v_nom=138)
    
    # Add generator with static values
    n.add("Generator", "gen_static", bus="bus1", carrier="gas", p_nom=100, marginal_cost=50)
    
    # Add generator with time-varying marginal cost
    n.add("Generator", "gen_timevar", bus="bus1", carrier="solar", p_nom=50, marginal_cost=0)
    
    # Add time-varying marginal cost data
    n.generators_t.marginal_cost = pd.DataFrame({
        'gen_timevar': [0, 5, 10, 0]  # Varies by hour
    }, index=n.snapshots)
    
    # Save to temporary NetCDF file
    netcdf_path = tmp_path / "timevar_network.nc"
    n.export_to_netcdf(netcdf_path)
    
    # Test parser
    parser = PypsaParser(netcdf_file=str(netcdf_path))
    system = parser.build_system()
    
    generators = list(system.get_components(PypsaGenerator))
    assert len(generators) == 2
    
    # Find generators by name
    gen_static = next(gen for gen in generators if gen.name == "gen_static")
    gen_timevar = next(gen for gen in generators if gen.name == "gen_timevar")
    
    # Check static generator (should be a scalar value under memory-efficient mode)
    assert isinstance(gen_static.marginal_cost, (float, int))
    assert float(gen_static.marginal_cost) == 50.0
    
    # Check time-varying generator
    assert isinstance(gen_timevar.marginal_cost, pd.Series)
    assert len(gen_timevar.marginal_cost) == 4  # 4 time periods
    assert gen_timevar.marginal_cost.iloc[0] == 0  # First hour
    assert gen_timevar.marginal_cost.iloc[1] == 5  # Second hour
    assert gen_timevar.marginal_cost.iloc[2] == 10  # Third hour
    assert gen_timevar.marginal_cost.iloc[3] == 0  # Fourth hour



