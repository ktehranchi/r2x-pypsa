import pytest
import pypsa
import pandas as pd
import logging
from pathlib import Path
from r2x.api import System

from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaStorageUnit, get_series_only

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
    
    # Add storage units
    n.add("StorageUnit", "storage1", bus="bus1", carrier="battery", p_nom=25, max_hours=4, 
          efficiency_store=0.9, efficiency_dispatch=0.9, marginal_cost=5)
    n.add("StorageUnit", "storage2", bus="bus2", carrier="pumped_hydro", p_nom=100, max_hours=8,
          efficiency_store=0.8, efficiency_dispatch=0.8, marginal_cost=2)
    
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





def test_bus_parsing(simple_netcdf_file):
    """Test that buses are parsed correctly."""
    parser = PypsaParser(netcdf_file=str(simple_netcdf_file))
    system = parser.build_system()
    
    # Check that buses were created
    buses = list(system.get_components(PypsaBus))
    assert len(buses) == 2  # bus1 and bus2 from fixture
    
    # Check first bus attributes
    bus1 = next(bus for bus in buses if bus.name == "bus1")
    assert bus1.carrier == "AC"
    assert bus1.v_nom == 138.0
    assert bus1.x == 0.0
    assert bus1.y == 0.0


def test_bus_model_creation():
    """Test PypsaBus model creation with minimal attributes."""
    bus = PypsaBus(
        name="test_bus",
        carrier="DC",
        v_nom=500.0
    )
    
    assert bus.name == "test_bus"
    assert bus.carrier == "DC"
    assert bus.v_nom == 500.0
    assert bus.x == 0.0  # default
    assert bus.y == 0.0  # default


def test_storage_unit_parsing(simple_netcdf_file):
    """Test that storage units are parsed correctly."""
    parser = PypsaParser(netcdf_file=str(simple_netcdf_file))
    system = parser.build_system()
    
    # Check that storage units were created
    storage_units = list(system.get_components(PypsaStorageUnit))
    assert len(storage_units) == 2  # storage1 and storage2 from fixture
    
    # Check first storage unit attributes
    storage1 = next(storage for storage in storage_units if storage.name == "storage1")
    assert storage1.bus == "bus1"
    assert storage1.carrier == "battery"
    assert storage1.p_nom == 25.0
    assert storage1.max_hours == 4.0
    assert storage1.efficiency_store == 0.9
    assert storage1.efficiency_dispatch == 0.9
    assert storage1.marginal_cost == 5.0
    
    # Check second storage unit attributes
    storage2 = next(storage for storage in storage_units if storage.name == "storage2")
    assert storage2.bus == "bus2"
    assert storage2.carrier == "pumped_hydro"
    assert storage2.p_nom == 100.0
    assert storage2.max_hours == 8.0
    assert storage2.efficiency_store == 0.8
    assert storage2.efficiency_dispatch == 0.8
    assert storage2.marginal_cost == 2.0


def test_storage_unit_model_creation():
    """Test PypsaStorageUnit model creation with minimal attributes."""
    storage = PypsaStorageUnit(
        name="test_storage",
        bus="bus1",
        p_nom=50.0,
        max_hours=4.0
    )
    
    assert storage.name == "test_storage"
    assert storage.bus == "bus1"
    assert storage.p_nom == 50.0
    assert storage.max_hours == 4.0
    assert storage.p_nom_extendable is False  # default
    assert storage.cyclic_state_of_charge is False  # default


