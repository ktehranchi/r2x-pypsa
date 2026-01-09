# Parsing Networks

This guide covers different methods for loading and parsing PyPSA networks.

## From NetCDF File

The standard approach for loading a PyPSA network:

```python
from r2x_pypsa.parser import PypsaParser

parser = PypsaParser(netcdf_file="path/to/network.nc")
system = parser.build_system()
```

## From Pre-loaded Network

Use an existing PyPSA network object:

```python
import pypsa
from r2x_pypsa.parser import PypsaParser

# Load network with PyPSA
network = pypsa.Network("network.nc")

# Optionally modify or optimize
network.optimize()

# Parse to R2X
parser = PypsaParser(network=network)
system = parser.build_system()
```

## With Weather Year

Specify a custom weather year for time series alignment:

```python
parser = PypsaParser(
    netcdf_file="network.nc",
    weather_year=2019
)
system = parser.build_system()
```

## Via R2X CLI

r2x-pypsa registers as an R2X plugin. Use the R2X CLI:

```bash
r2x parse --parser r2x_pypsaParser --netcdf-file-path network.nc
```

## Accessing Parsed Components

After parsing, access components by type:

```python
from r2x_pypsa.models import (
    PypsaGenerator,
    PypsaBus,
    PypsaLoad,
    PypsaStorageUnit,
    PypsaLine,
    PypsaLink,
    PypsaStore
)

# Get specific component types
generators = list(system.get_components(PypsaGenerator))
buses = list(system.get_components(PypsaBus))
loads = list(system.get_components(PypsaLoad))
storage = list(system.get_components(PypsaStorageUnit))
lines = list(system.get_components(PypsaLine))
links = list(system.get_components(PypsaLink))
stores = list(system.get_components(PypsaStore))

print(f"Parsed: {len(generators)} generators, {len(buses)} buses")
```

## Filtering Components

Filter components by carrier or other attributes:

```python
# Get only solar generators
solar_gens = [
    g for g in system.get_components(PypsaGenerator)
    if g.carrier.value == "solar"
]

# Get thermal generators
thermal_gens = [
    g for g in system.get_components(PypsaGenerator)
    if g.carrier.value in ["gas", "coal", "nuclear"]
]
```

## Handling Parsing Errors

The parser logs warnings for components that fail to parse:

```python
import logging

# Enable debug logging to see all parsing details
logging.basicConfig(level=logging.DEBUG)

parser = PypsaParser(netcdf_file="network.nc")
system = parser.build_system()
```

Components that fail to parse are skipped, and a warning is logged with details about the failure.
