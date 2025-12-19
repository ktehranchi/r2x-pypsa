import pytest
import warnings
from pathlib import Path

DATA_FOLDER = "tests/data"
SIMPLE_NETCDF = "test_simple_network.nc"

# Suppress warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="infrasys.*")
warnings.filterwarnings("ignore", message=".*field_name.*deprecated.*")
warnings.filterwarnings("ignore", message=".*default_factory.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*numpy.*")


@pytest.fixture
def simple_netcdf(pytestconfig: pytest.Config) -> Path:
    """Fixture providing path to the simple NetCDF test file."""
    netcdf_path = pytestconfig.rootpath.joinpath(DATA_FOLDER).joinpath(SIMPLE_NETCDF)
    return netcdf_path
