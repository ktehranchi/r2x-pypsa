from r2x.api import System
from infrasys import TimeSeriesStorageType
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization.to_sienna import infrasys_to_psy
from loguru import logger

from pathlib import Path
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import create_default_mapping

# Use the test data
test_file = Path("tests/data/test_simple_network.nc")
parser = PypsaParser(netcdf_file=str(test_file))
pypsa_system = parser.build_system()

# Convert to Sienna
mapping = create_default_mapping()


# Create a new PSY system
psy_system = System(
    name="PSY system",
    auto_add_composed_components=True,
    time_series_storage_type=TimeSeriesStorageType.HDF5
)

# Convert all PyPSA components to PSY components
for component in pypsa_system._component_mgr.iter_all():
    try:
        pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
    except Exception as e:
        logger.warning(f"Failed to convert component {component.name}: {e}")
        continue

# Serialize the PSY system to Sienna format
infrasys_to_psy(psy_system, filename="test_output.json")