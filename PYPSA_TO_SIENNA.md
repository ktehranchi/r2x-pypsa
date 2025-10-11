# PyPSA Network to Sienna JSON Conversion Guide

This guide explains how to use the `r2x-pypsa` parser to convert PyPSA network files (NetCDF format) to Sienna JSON format, which is compatible with PowerSystems.jl and other Sienna tools.

## About the Parser

The main parser implementation is located in `src/r2x_pypsa/parser.py` and provides the `PypsaParser` class. This class handles:
- Loading PyPSA networks from NetCDF files
- Parsing all PyPSA component types (buses, generators, loads, lines, links, storage, etc.)
- Converting static and time-varying attributes
- Building an R2X System that can be exported to Sienna format

The serialization functionality (converting to Sienna JSON) is in `src/r2x_pypsa/serialization/`.

## Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Usage](#detailed-usage)
- [Component Mapping](#component-mapping)
- [Customizing the Conversion](#customizing-the-conversion)
- [Troubleshooting](#troubleshooting)
- [Examples](#examples)

## Overview

The conversion process involves two main steps:
1. **Parse PyPSA Network**: Load a PyPSA network from a NetCDF file and convert it to the R2X System format
2. **Export to Sienna**: Convert the R2X System to Sienna JSON format

The `r2x-pypsa` package provides the `PypsaParser` class for the first step and the `pypsa_to_sienna` function for the second step.

## Prerequisites

### Required Dependencies
- Python >= 3.11
- `r2x` package
- `pypsa` == 0.35.2
- `pandas`
- `loguru`

### Input Requirements
- A PyPSA network file in NetCDF format (`.nc` extension)
- The network should contain standard PyPSA components (buses, generators, loads, lines, links, storage units, stores)

## Quick Start

Here's the simplest way to convert a PyPSA network to Sienna JSON:

```python
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
```

After running this code, you'll have:
- `output/sienna_system.json`: The main Sienna system file
- `output/time_series_storage.h5`: Time series data in HDF5 format
- `output/time_series_storage_metadata.db`: Time series metadata

## Detailed Usage

### Step 1: Parsing PyPSA Networks

The `PypsaParser` class handles loading and converting PyPSA networks:

```python
from r2x_pypsa.parser import PypsaParser

# Initialize the parser
parser = PypsaParser(
    netcdf_file="path/to/network.nc",
    weather_year=2030  # Optional: specify a weather year
)

# Build the R2X system
system = parser.build_system()
```

#### What Gets Parsed

The parser extracts and converts the following PyPSA components:

- **Buses**: Network nodes with voltage levels and locations
- **Generators**: Power generation units (thermal, renewable, etc.)
- **Storage Units**: Energy storage with charge/discharge capabilities
- **Stores**: Simple energy storage containers
- **Links**: Bidirectional power connections between buses
- **Lines**: AC transmission lines with impedance characteristics
- **Loads**: Power consumption at buses

#### Time Series Data

The parser automatically handles both static and time-varying attributes:
- Static values (e.g., `p_nom` - nominal power)
- Time series data (e.g., `p_max_pu_t` - maximum power per unit over time)

All time-varying data from the PyPSA network is preserved in the R2X system.

### Step 2: Converting to Sienna JSON

Once you have an R2X system, convert it to Sienna format:

```python
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

# Create a mapping configuration (optional but recommended)
mapping = create_default_mapping()

# Convert to Sienna
pypsa_to_sienna(
    pypsa_system=system,
    output_path="output/sienna_system.json",
    mapping=mapping
)
```

## Component Mapping

The conversion uses carrier types to map PyPSA components to Sienna component types. The default mapping includes:

### Generator Mapping (by carrier)

| PyPSA Carrier | Sienna Type | Prime Mover | Fuel Type |
|---------------|-------------|-------------|-----------|
| coal | ThermalStandard | Steam Turbine (ST) | COAL |
| gas | ThermalStandard | Gas Turbine (GT) | NATURAL_GAS |
| nuclear | ThermalStandard | Steam Turbine (ST) | NUCLEAR |
| oil | ThermalStandard | Internal Combustion (IC) | DISTILLATE_FUEL_OIL |
| solar | RenewableDispatch | Photovoltaic (PVe) | - |
| onwind | RenewableDispatch | Wind Turbine (WT) | - |
| offwind | RenewableDispatch | Wind Turbine (WT) | - |
| hydro | HydroDispatch | Hydro (HY) | - |
| battery | EnergyReservoirStorage | Battery (BA) | - |
| pumped_hydro | HydroPumpedStorage | Hydro (HY) | - |
| OCGT | ThermalStandard | Gas Turbine (GT) | NATURAL_GAS |
| CCGT | ThermalStandard | Gas Turbine (GT) | NATURAL_GAS |

### Other Component Mappings

- **PypsaBus** → **ACBus** (AC bus in Sienna)
- **PypsaLoad** → **PowerLoad** (Standard power load)
- **PypsaLine** → **Line** (AC transmission line)
- **PypsaStore** → **EnergyReservoirStorage** (Simple energy storage)

## Customizing the Conversion

### Custom Component Mapping

You can customize the mapping to match your specific PyPSA network:

```python
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

pypsa_to_sienna(
    pypsa_system=system,
    output_path="output/sienna_system.json",
    mapping=custom_mapping
)
```

### Filtering Components

You can filter which components to include in the conversion:

```python
from r2x_pypsa.models import PypsaGenerator, PypsaBus

# Get only specific component types
generators = list(system.get_components(PypsaGenerator))
buses = list(system.get_components(PypsaBus))

# Filter by attributes
coal_generators = [g for g in generators if g.carrier.get_value() == "coal"]
```

## Troubleshooting

### Common Issues

#### 1. NetCDF File Not Found
```
FileNotFoundError: PyPSA netcdf file not found: path/to/network.nc
```
**Solution**: Verify the path to your NetCDF file and ensure it exists.

#### 2. Missing Carrier Information
```
Failed to convert component gen1: Missing carrier information
```
**Solution**: Ensure all generators in your PyPSA network have a `carrier` attribute set. You can set default carriers before conversion.

#### 3. Time Series Mismatch
```
Warning: Time series length mismatch for component ...
```
**Solution**: Ensure all time series in your PyPSA network have consistent time indices. Check `network.snapshots` for consistency.

#### 4. Unknown Carrier Type
```
Warning: Unknown carrier type 'custom_type', using default mapping
```
**Solution**: Add the carrier type to your custom mapping or use a standard carrier name.

### Validation

After conversion, validate the Sienna JSON file:

```python
from r2x.api import System
from infrasys import TimeSeriesStorageType

# Load the Sienna system
sienna_system = System()
sienna_system.from_json("output/sienna_system.json")

# Check components
from r2x.models import ThermalStandard, ACBus
buses = list(sienna_system.get_components(ACBus))
generators = list(sienna_system.get_components(ThermalStandard))

print(f"Loaded {len(buses)} buses and {len(generators)} generators")
```

## Examples

### Example 1: Basic Conversion

```python
from pathlib import Path
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

# Parse PyPSA network
parser = PypsaParser(netcdf_file="data/my_network.nc")
system = parser.build_system()

# Convert to Sienna
mapping = create_default_mapping()
pypsa_to_sienna(
    pypsa_system=system,
    output_path="output/sienna_system.json",
    mapping=mapping
)

print("Conversion complete!")
```

### Example 2: Conversion with Logging

```python
from loguru import logger
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

# Configure logging
logger.add("conversion.log", level="DEBUG")

# Parse with logging
logger.info("Starting PyPSA to Sienna conversion")
parser = PypsaParser(netcdf_file="data/my_network.nc")
system = parser.build_system()

# Log component counts
from infrasys.component import Component
from r2x_pypsa.models import PypsaGenerator, PypsaBus

total_components = len(list(system.get_components(Component)))
generators = len(list(system.get_components(PypsaGenerator)))
buses = len(list(system.get_components(PypsaBus)))

logger.info(f"Parsed {total_components} total components")
logger.info(f"  - {buses} buses")
logger.info(f"  - {generators} generators")

# Convert to Sienna
mapping = create_default_mapping()
pypsa_to_sienna(
    pypsa_system=system,
    output_path="output/sienna_system.json",
    mapping=mapping
)

logger.info("Conversion complete!")
```

### Example 3: Batch Conversion

```python
from pathlib import Path
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

# Directory containing PyPSA network files
input_dir = Path("data/pypsa_networks")
output_dir = Path("output/sienna_systems")
output_dir.mkdir(exist_ok=True)

mapping = create_default_mapping()

# Convert all NetCDF files
for netcdf_file in input_dir.glob("*.nc"):
    print(f"Converting {netcdf_file.name}...")
    
    try:
        # Parse
        parser = PypsaParser(netcdf_file=str(netcdf_file))
        system = parser.build_system()
        
        # Convert
        output_path = output_dir / f"{netcdf_file.stem}_sienna.json"
        pypsa_to_sienna(
            pypsa_system=system,
            output_path=str(output_path),
            mapping=mapping
        )
        
        print(f"  ✓ Saved to {output_path}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
```

### Example 4: Using the Demo Script

The repository includes a demo script for testing the parser:

```bash
# Run with default test data
python tests/test_demo_parser.py

# Run with your own network file
python tests/test_demo_parser.py --netcdf-file-path /path/to/your/network.nc

# Enable verbose logging
python tests/test_demo_parser.py --netcdf-file-path /path/to/your/network.nc --verbose
```

The demo script will:
1. Parse the PyPSA network
2. Display a summary of all components
3. Show details of the first few buses, generators, loads, etc.
4. Create a log file with detailed information

### Example 5: Working with Time Series

```python
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.models import PypsaGenerator

# Parse network with time series data
parser = PypsaParser(netcdf_file="data/network_with_timeseries.nc")
system = parser.build_system()

# Access generator time series
generators = list(system.get_components(PypsaGenerator))
for gen in generators[:3]:  # First 3 generators
    print(f"\nGenerator: {gen.name}")
    print(f"  Carrier: {gen.carrier.get_value()}")
    print(f"  Nominal Power: {gen.p_nom.get_value()} MW")
    
    # Check if marginal_cost has time series
    if gen.marginal_cost.time_series is not None:
        ts = gen.marginal_cost.time_series
        print(f"  Marginal Cost: Time series with {len(ts)} points")
        print(f"    Min: {ts.min():.2f}, Max: {ts.max():.2f}, Mean: {ts.mean():.2f}")
    else:
        print(f"  Marginal Cost: {gen.marginal_cost.get_value()} (static)")

# Convert to Sienna (time series are preserved)
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

mapping = create_default_mapping()
pypsa_to_sienna(
    pypsa_system=system,
    output_path="output/sienna_with_timeseries.json",
    mapping=mapping
)
```

## Additional Resources

### API Reference

- **PypsaParser**: See `src/r2x_pypsa/parser.py`
- **Serialization Functions**: See `src/r2x_pypsa/serialization/api.py`
- **Component Models**: See `src/r2x_pypsa/models/`

### Related Documentation

- [PyPSA Documentation](https://pypsa.readthedocs.io/)
- [Sienna Documentation](https://nrel-sienna.github.io/PowerSystems.jl/stable/)
- [R2X Documentation](https://github.com/NREL/r2x)

### Testing

Run the test suite to verify your installation:

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_parser.py

# Run with verbose output
pytest tests/ -v
```

### Contributing

If you encounter issues or have suggestions for improving the conversion:
1. Check existing issues on GitHub
2. Create a new issue with a minimal example
3. Include your PyPSA network file (if possible) or a minimal reproducible example

## Summary

This guide covered:
- ✓ Loading PyPSA networks from NetCDF files
- ✓ Converting PyPSA networks to R2X System format
- ✓ Exporting R2X Systems to Sienna JSON format
- ✓ Customizing component mappings
- ✓ Working with time series data
- ✓ Troubleshooting common issues

For more advanced usage and customization options, refer to the source code documentation and examples in the `tests/` directory.
