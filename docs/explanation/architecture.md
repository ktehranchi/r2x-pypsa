# Architecture

This document explains the architecture of r2x-pypsa and how data flows through the system.

## Overview

r2x-pypsa follows a two-stage conversion pipeline:

```
PyPSA Network (NetCDF) → R2X System → Sienna System (JSON/H5)
```

1. **Parsing Stage**: PyPSA networks are parsed into R2X System objects
2. **Serialization Stage**: R2X components are converted to PowerSystems.jl format

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        r2x-pypsa                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────────┐  │
│  │   PyPSA      │     │    R2X       │     │   Sienna       │  │
│  │   Network    │────▶│   System     │────▶│   JSON/H5      │  │
│  │   (NetCDF)   │     │              │     │                │  │
│  └──────────────┘     └──────────────┘     └────────────────┘  │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────────┐  │
│  │ PypsaParser  │     │ PyPSA Models │     │ pypsa_to_psy   │  │
│  │              │     │ (Generator,  │     │ serialization  │  │
│  │ _process_*() │     │  Bus, Load,  │     │                │  │
│  │              │     │  Storage...) │     │                │  │
│  └──────────────┘     └──────────────┘     └────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Parsing Stage

### PypsaParser

The `PypsaParser` class is responsible for loading PyPSA networks and converting them to R2X System objects.

**Key Methods:**

- `build_system()` - Main entry point that orchestrates parsing
- `_process_buses()` - Converts PyPSA buses to PypsaBus components
- `_process_generators()` - Converts generators to PypsaGenerator components
- `_process_storage_units()` - Converts storage units to PypsaStorageUnit
- `_process_loads()` - Converts loads to PypsaLoad components
- `_process_lines()` - Converts AC lines to PypsaLine components
- `_process_links()` - Converts DC links to PypsaLink components
- `_process_stores()` - Converts stores to PypsaStore components

### Time Series Handling

PyPSA stores time-varying data in separate DataFrames (e.g., `network.generators_t.p_max_pu`). The parser uses `get_switchable_as_dense()` to retrieve this data and creates `PypsaProperty` objects that can hold either static values or time series.

```python
# Time-varying data is wrapped in PypsaProperty
p_max_pu = get_ts_or_static(network, 'generators_t', 'p_max_pu', gen_name, ...)
```

## Serialization Stage

### Component Conversion

The serialization module uses Python's `singledispatch` pattern to handle different component types:

```python
@singledispatch
def pypsa_component_to_psy(component, system):
    """Convert a PyPSA component to PSY format."""
    raise NotImplementedError(f"No converter for {type(component)}")

@pypsa_component_to_psy.register(PypsaGenerator)
def _(component, system):
    # Convert generator to ThermalStandard, RenewableDispatch, etc.
    ...
```

### Cost Model Creation

The `create_operational_cost()` function creates appropriate cost models:

- **ThermalGenerationCost** - For thermal generators with marginal costs
- **RenewableCost** - For renewable generators (typically zero marginal cost)
- **HydroCost** - For hydro generators

### Output Format

The final output uses PowerSystems.jl's serialization format:

- **JSON file**: Contains component definitions, topology, and metadata
- **HDF5 file**: Contains time series data in an efficient binary format

## R2X Plugin Integration

r2x-pypsa registers as an R2X plugin, enabling CLI integration:

```python
@PluginManager.register_cli("parser", "r2x_pypsaParser")
def cli_arguments(parser: ArgumentParser):
    parser.add_argument("--netcdf-file-path", ...)
```

This allows using the standard R2X CLI:

```bash
r2x parse --parser r2x_pypsaParser --netcdf-file-path network.nc
```

## Extension Points

### Adding New Component Types

To support a new PyPSA component type:

1. Create a model class in `r2x_pypsa/models/`
2. Add a `_process_*()` method in `PypsaParser`
3. Register a converter in `pypsa_to_psy.py`

### Custom Cost Models

The cost model creation can be customized by modifying `cost_models.py` or by post-processing the R2X system before serialization.
