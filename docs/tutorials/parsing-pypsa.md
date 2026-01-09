# Parsing PyPSA Networks

This tutorial teaches you how to load PyPSA networks and parse them into R2X System format using r2x-pypsa.

## What You'll Learn

- How to initialize the PypsaParser
- How to load networks from NetCDF files
- How to use pre-loaded PyPSA network objects
- How to inspect the parsed system

## Loading from a NetCDF File

The most common way to use r2x-pypsa is to load a PyPSA network from a NetCDF file:

```python
from r2x_pypsa.parser import PypsaParser

# Initialize the parser with a NetCDF file path
parser = PypsaParser(netcdf_file="path/to/network.nc")

# Build the R2X System
system = parser.build_system()

# Inspect the system
print(f"Total components: {len(list(system.get_components()))}")
```

## Using a Pre-loaded Network

If you already have a PyPSA network object (e.g., after running an optimization), you can pass it directly:

```python
import pypsa
from r2x_pypsa.parser import PypsaParser

# Load and optionally modify the PyPSA network
network = pypsa.Network("path/to/network.nc")

# Run PyPSA optimization (optional)
network.optimize()

# Parse the optimized network
parser = PypsaParser(network=network)
system = parser.build_system()
```

## Inspecting Parsed Components

Once you have a system, you can inspect its components:

```python
from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaLoad, PypsaStorageUnit

# Get all generators
generators = list(system.get_components(PypsaGenerator))
print(f"Generators: {len(generators)}")

# Get all buses
buses = list(system.get_components(PypsaBus))
print(f"Buses: {len(buses)}")

# Get all loads
loads = list(system.get_components(PypsaLoad))
print(f"Loads: {len(loads)}")

# Get all storage units
storage = list(system.get_components(PypsaStorageUnit))
print(f"Storage units: {len(storage)}")
```

## Component Properties

Each parsed component contains the full set of PyPSA attributes. For example, a generator has:

```python
# Get a specific generator
gen = next(system.get_components(PypsaGenerator))

# Access properties
print(f"Name: {gen.name}")
print(f"Bus: {gen.bus}")
print(f"Carrier: {gen.carrier.value}")
print(f"Nominal power: {gen.p_nom.value} MW")
print(f"Marginal cost: {gen.marginal_cost.value}")
```

## Time Series Data

Many PyPSA components have time-varying data. r2x-pypsa preserves this:

```python
# Check if a property has time series data
if gen.p_max_pu.is_time_series:
    print("p_max_pu is time-varying")
    ts_data = gen.p_max_pu.time_series
    print(f"Time series length: {len(ts_data)}")
else:
    print(f"p_max_pu is static: {gen.p_max_pu.value}")
```

## Next Steps

Now that you know how to parse PyPSA networks, learn how to [convert them to Sienna format](converting-to-sienna.md).
