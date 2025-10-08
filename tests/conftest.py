import pytest
from pathlib import Path

DATA_FOLDER = "tests/data"
SIMPLE_NETCDF = "test_simple_network.nc"


@pytest.fixture
def simple_netcdf(pytestconfig: pytest.Config) -> Path:
    """Fixture providing path to the simple NetCDF test file."""
    netcdf_path = pytestconfig.rootpath.joinpath(DATA_FOLDER).joinpath(SIMPLE_NETCDF)
    return netcdf_path
