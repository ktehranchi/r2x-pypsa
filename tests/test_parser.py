import pytest
import pypsa
import pandas as pd
import logging
from pathlib import Path
from r2x.api import System

from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.models import PypsaGenerator, get_series_only

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


def test_all_generator_attributes_present(simple_parser: PypsaParser) -> None:
    """Test that all PyPSA generator attributes are properly mapped and accessible."""
    parser = simple_parser
    system = parser.build_system()
    
    generators = list(system.get_components(PypsaGenerator))
    assert len(generators) > 0
    
    # Test on first generator
    gen = generators[0]
    
    # Required attributes
    assert hasattr(gen, 'name')
    assert hasattr(gen, 'bus')
    assert isinstance(gen.name, str)
    assert isinstance(gen.bus, str)
    
    # Static attributes
    assert hasattr(gen, 'control')
    assert hasattr(gen, 'type')
    assert hasattr(gen, 'p_nom')
    assert hasattr(gen, 'p_nom_mod')
    assert hasattr(gen, 'p_nom_extendable')
    assert hasattr(gen, 'p_nom_min')
    assert hasattr(gen, 'p_nom_max')
    assert hasattr(gen, 'e_sum_min')
    assert hasattr(gen, 'e_sum_max')
    assert hasattr(gen, 'sign')
    assert hasattr(gen, 'carrier')
    assert hasattr(gen, 'active')
    assert hasattr(gen, 'build_year')
    assert hasattr(gen, 'lifetime')
    assert hasattr(gen, 'capital_cost')
    
    # Unit commitment attributes
    assert hasattr(gen, 'committable')
    assert hasattr(gen, 'start_up_cost')
    assert hasattr(gen, 'shut_down_cost')
    assert hasattr(gen, 'stand_by_cost')
    assert hasattr(gen, 'min_up_time')
    assert hasattr(gen, 'min_down_time')
    assert hasattr(gen, 'up_time_before')
    assert hasattr(gen, 'down_time_before')
    assert hasattr(gen, 'ramp_limit_up')
    assert hasattr(gen, 'ramp_limit_down')
    assert hasattr(gen, 'ramp_limit_start_up')
    assert hasattr(gen, 'ramp_limit_shut_down')
    assert hasattr(gen, 'weight')
    
    # Time-varying attributes (can be float or Series)
    assert hasattr(gen, 'p_min_pu')
    assert hasattr(gen, 'p_max_pu')
    assert hasattr(gen, 'p_set')
    assert hasattr(gen, 'q_set')
    assert hasattr(gen, 'marginal_cost')
    assert hasattr(gen, 'marginal_cost_quadratic')
    assert hasattr(gen, 'efficiency')
    assert hasattr(gen, 'stand_by_cost')
    
    # Output attributes
    assert hasattr(gen, 'p')
    assert hasattr(gen, 'q')
    assert hasattr(gen, 'p_nom_opt')
    assert hasattr(gen, 'status')
    assert hasattr(gen, 'start_up')
    assert hasattr(gen, 'shut_down')
    assert hasattr(gen, 'mu_upper')
    assert hasattr(gen, 'mu_lower')
    assert hasattr(gen, 'mu_p_set')
    assert hasattr(gen, 'mu_ramp_limit_up')
    assert hasattr(gen, 'mu_ramp_limit_down')


def test_generator_attribute_defaults(simple_parser: PypsaParser) -> None:
    """Test that missing attributes get proper default values."""
    parser = simple_parser
    system = parser.build_system()
    
    generators = list(system.get_components(PypsaGenerator))
    gen = generators[0]
    
    # Test default values for static attributes
    assert gen.control == "PQ"  # Default control strategy
    assert gen.p_nom_extendable is False  # Default not extendable
    assert gen.p_nom_min == 0.0  # Default minimum
    assert gen.p_nom_max == float('inf')  # Default maximum
    assert gen.e_sum_min == float('-inf')  # Default minimum energy
    assert gen.e_sum_max == float('inf')  # Default maximum energy
    assert gen.sign == 1.0  # Default sign
    assert gen.active is True  # Default active
    assert gen.build_year == 0  # Default build year
    assert gen.lifetime == float('inf')  # Default lifetime
    assert gen.capital_cost == 0.0  # Default capital cost
    
    # Test default values for unit commitment attributes
    assert gen.committable is False  # Default not committable
    assert gen.start_up_cost == 0.0  # Default start up cost
    assert gen.shut_down_cost == 0.0  # Default shut down cost
    assert gen.stand_by_cost == 0.0  # Default stand by cost
    assert gen.min_up_time == 0  # Default min up time
    assert gen.min_down_time == 0  # Default min down time
    assert gen.up_time_before == 1  # Default up time before
    assert gen.down_time_before == 0  # Default down time before
    assert gen.ramp_limit_start_up == 1.0  # Default ramp limit start up
    assert gen.ramp_limit_shut_down == 1.0  # Default ramp limit shut down
    assert gen.weight == 1.0  # Default weight
    
    # Test default values for time-varying attributes
    assert gen.p_min_pu == 0.0  # Default minimum power
    assert gen.p_max_pu == 1.0  # Default maximum power
    assert gen.p_set == 0.0  # Default power set point
    assert gen.q_set == 0.0  # Default reactive power set point
    assert gen.marginal_cost == 0.0  # Default marginal cost
    assert gen.marginal_cost_quadratic == 0.0  # Default quadratic marginal cost
    assert gen.efficiency == 1.0  # Default efficiency
    assert gen.stand_by_cost == 0.0  # Default stand by cost
    
    # Test series-only attributes (always pd.Series)
    assert isinstance(gen.p, pd.Series)  # Active power is always a Series
    assert isinstance(gen.q, pd.Series)  # Reactive power is always a Series
    assert isinstance(gen.status, pd.Series)  # Status is always a Series
    assert isinstance(gen.start_up, pd.Series)  # Start up is always a Series
    assert isinstance(gen.shut_down, pd.Series)  # Shut down is always a Series
    assert isinstance(gen.mu_upper, pd.Series)  # Shadow price upper is always a Series
    assert isinstance(gen.mu_lower, pd.Series)  # Shadow price lower is always a Series
    assert isinstance(gen.mu_p_set, pd.Series)  # Shadow price p_set is always a Series
    assert isinstance(gen.mu_ramp_limit_up, pd.Series)  # Shadow price ramp up is always a Series
    assert isinstance(gen.mu_ramp_limit_down, pd.Series)  # Shadow price ramp down is always a Series


def test_generator_unit_commitment_attributes(tmp_path):
    """Test unit commitment specific attributes."""
    # Create network with unit commitment generator
    n = pypsa.Network()
    n.snapshots = pd.date_range("2023-01-01", periods=4, freq="h")
    
    # Add buses
    n.add("Bus", "bus1", carrier="AC", v_nom=138)
    
    # Add generator with unit commitment attributes
    n.add("Generator", "gen_uc", 
          bus="bus1", 
          carrier="gas", 
          p_nom=100, 
          marginal_cost=50,
          committable=True,
          start_up_cost=1000,
          shut_down_cost=500,
          min_up_time=2,
          min_down_time=1,
          up_time_before=1,
          down_time_before=0,
          ramp_limit_start_up=0.5,
          ramp_limit_shut_down=0.3)
    
    # Save to temporary NetCDF file
    netcdf_path = tmp_path / "uc_network.nc"
    n.export_to_netcdf(netcdf_path)
    
    # Test parser
    parser = PypsaParser(netcdf_file=str(netcdf_path))
    system = parser.build_system()
    
    generators = list(system.get_components(PypsaGenerator))
    assert len(generators) == 1
    
    gen = generators[0]
    
    # Test unit commitment attributes are properly set
    assert gen.committable is True
    assert gen.start_up_cost == 1000.0
    assert gen.shut_down_cost == 500.0
    assert gen.min_up_time == 2
    assert gen.min_down_time == 1
    assert gen.up_time_before == 1
    assert gen.down_time_before == 0
    assert gen.ramp_limit_start_up == 0.5
    assert gen.ramp_limit_shut_down == 0.3


def test_get_series_only_function():
    """Test the get_series_only helper function directly."""
    
    # Create a simple network for testing
    n = pypsa.Network()
    n.snapshots = pd.date_range("2023-01-01", periods=3, freq="h")
    n.add("Bus", "bus1", carrier="AC", v_nom=138)
    n.add("Generator", "gen1", bus="bus1", carrier="solar", p_nom=100)
    
    # Add some series data to the generator using proper pandas assignment
    n.generators_t.p = pd.DataFrame({
        'gen1': [10.0, 20.0, 30.0]
    }, index=n.snapshots)
    
    # Test with existing component
    result = get_series_only(n, 'gen1', 'p', 0.0)
    assert isinstance(result, pd.Series)
    assert len(result) == 3
    assert result.iloc[0] == 10.0
    assert result.iloc[1] == 20.0
    assert result.iloc[2] == 30.0
    
    # Test with non-existing component (should create default series)
    result = get_series_only(n, 'gen2', 'p', 99.0)
    assert isinstance(result, pd.Series)
    assert len(result) == 3
    assert all(result == 99.0)
    assert result.index.equals(n.snapshots)



