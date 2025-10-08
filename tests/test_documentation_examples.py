"""
Test to validate documentation examples are syntactically correct.

This file ensures that the code examples in the documentation can be parsed
and that all imports are valid.
"""

def test_quick_start_example():
    """Test the Quick Start example from PYPSA_TO_SIENNA.md"""
    
    # This is the example code from the documentation
    example_code = """
from pathlib import Path
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

# Step 1: Parse the PyPSA network
parser = PypsaParser(netcdf_file="path/to/your/network.nc")
pypsa_system = parser.build_system()

# Step 2: Convert to Sienna JSON
mapping = create_default_mapping()
pypsa_to_sienna(
    pypsa_system=pypsa_system,
    output_path="output/sienna_system.json",
    mapping=mapping
)
"""
    
    # Just verify it compiles
    compile(example_code, '<string>', 'exec')


def test_detailed_usage_example():
    """Test the Detailed Usage example from PYPSA_TO_SIENNA.md"""
    
    example_code = """
from r2x_pypsa.parser import PypsaParser

# Initialize the parser
parser = PypsaParser(
    netcdf_file="path/to/network.nc",
    weather_year=2030  # Optional: specify a weather year
)

# Build the R2X system
system = parser.build_system()
"""
    
    compile(example_code, '<string>', 'exec')


def test_conversion_example():
    """Test the conversion example from PYPSA_TO_SIENNA.md"""
    
    example_code = """
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

# Create a mapping configuration (optional but recommended)
mapping = create_default_mapping()

# Convert to Sienna
pypsa_to_sienna(
    pypsa_system=system,
    output_path="output/sienna_system.json",
    mapping=mapping
)
"""
    
    compile(example_code, '<string>', 'exec')


def test_custom_mapping_example():
    """Test the custom mapping example from PYPSA_TO_SIENNA.md"""
    
    example_code = """
from r2x.models import ThermalStandard, RenewableDispatch
from r2x.enums import PrimeMoversType, ThermalFuels

custom_mapping = {
    "generator_mapping": {
        "my_custom_coal": ThermalStandard,
        "my_wind_type": RenewableDispatch,
    },
    "prime_mover_mapping": {
        "my_custom_coal": PrimeMoversType.ST,
        "my_wind_type": PrimeMoversType.WT,
    },
    "fuel_mapping": {
        "my_custom_coal": ThermalFuels.COAL,
        "my_wind_type": ThermalFuels.OTHER,
    }
}
"""
    
    compile(example_code, '<string>', 'exec')


def test_imports_are_valid():
    """Test that all imports mentioned in the documentation are valid."""
    
    # Test parser imports
    from r2x_pypsa.parser import PypsaParser
    from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping
    from r2x_pypsa.models import (
        PypsaGenerator, PypsaBus, PypsaLoad, 
        PypsaLine, PypsaLink, PypsaStorageUnit, PypsaStore
    )
    from infrasys.component import Component
    from r2x.api import System
    from r2x.models import (
        ThermalStandard, RenewableDispatch, HydroDispatch,
        EnergyReservoirStorage, HydroPumpedStorage, ACBus, PowerLoad, Line
    )
    from r2x.enums import PrimeMoversType, ThermalFuels
    
    # Verify classes exist
    assert PypsaParser is not None
    assert pypsa_to_sienna is not None
    assert create_default_mapping is not None
    assert PypsaGenerator is not None
    assert PypsaBus is not None
    assert ThermalStandard is not None
    assert PrimeMoversType is not None


if __name__ == "__main__":
    # Run all tests
    test_quick_start_example()
    test_detailed_usage_example()
    test_conversion_example()
    test_custom_mapping_example()
    test_imports_are_valid()
    
    print("✓ All documentation examples are syntactically valid")
    print("✓ All imports are valid")
