# r2x-pypsa

A PyPSA to Sienna converter and parser that enables interoperability between [PyPSA](https://pypsa.org/) (Python for Power System Analysis) and [Sienna](https://www.nrel.gov/analysis/sienna.html) (Julia-based power system modeling framework).

## Overview

r2x-pypsa serves as a bridge between PyPSA and the R2X/Sienna ecosystem, enabling:

- **Parsing**: Convert PyPSA networks (from NetCDF format) into R2X System objects
- **Conversion**: Transform PyPSA power system components to PowerSystems.jl (Sienna) compatible format
- **Validation**: Enable economic dispatch validation between PyPSA and Sienna solvers
- **Round-trip analysis**: Compare optimization results across different modeling platforms

This package integrates with the [R2X framework](https://github.com/NREL/R2X) as a plugin, providing parser and exporter capabilities for PyPSA networks.

> **Note: Current Transmission Model Limitations**
>
> r2x-pypsa currently only supports **zonal (AreaInterchange) transmission models**. PyPSA `Link` components are converted to Sienna `AreaInterchange` objects representing inter-area power transfer limits.
>
> The following transmission models are **not yet supported**:
>
> - AC transmission lines (`Line` → `ACBranch`)
> - HVDC lines (`Link` with HVDC characteristics → `TwoTerminalHVDCLine`)

## Features

- Full support for PyPSA component types:
  - Generators (thermal, renewable, hydro)
  - Storage Units (batteries, pumped hydro)
  - Buses and transmission networks (Lines, Links)
  - Loads (static and time-varying)
  - Stores (energy storage without power constraints)
- Time series handling for dynamic data
- Cost model conversion for economic dispatch
- Comprehensive validation tools for comparing dispatch results

## Installation

### Prerequisites

- Python >= 3.11
- [uv](https://github.com/astral-sh/uv) package manager (recommended)

### Install from source

```bash
git clone https://github.com/ktehranchi/r2x-pypsa.git
cd r2x-pypsa
uv sync
```

## Quick Start

### Basic Usage

```python
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna

# Load a PyPSA network and convert to R2X System
parser = PypsaParser(netcdf_file="path/to/network.nc")
system = parser.build_system()

# Convert to Sienna format
pypsa_to_sienna(system, output_path="output/sienna_system")
```

### Using with a pre-loaded PyPSA network

```python
import pypsa
from r2x_pypsa.parser import PypsaParser

# Load PyPSA network
network = pypsa.Network("path/to/network.nc")

# Optionally run PyPSA optimization
network.optimize()

# Convert to R2X System
parser = PypsaParser(network=network)
system = parser.build_system()
```

## Validation Workflow

The standard PyPSA to Sienna validation workflow consists of three steps:

```bash
# 1. Convert PyPSA to Sienna JSON and run PyPSA Economic Dispatch
uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch -v

# 2. Run Sienna Economic Dispatch (Julia)
julia tests/julia/run_sienna_ed.jl tests/test_output/test_network_1h_output_optimized.json tests/test_output/sienna_objective.txt

# 3. Compare objectives
uv run pytest tests/test_end_to_end.py::test_pypsa_sienna_objective_match -v
```

## Documentation

Full documentation is available at [https://ktehranchi.github.io/r2x-pypsa/](https://ktehranchi.github.io/r2x-pypsa/)

## Related Projects

- [R2X](https://github.com/NREL/R2X) - The R2X framework for power system model translation
- [PyPSA](https://pypsa.org/) - Python for Power System Analysis
- [Sienna](https://www.nrel.gov/analysis/sienna.html) - Scalable Integrated Electric Network Analysis
- [PowerSystems.jl](https://github.com/NREL-Sienna/PowerSystems.jl) - Julia package for power system modeling

## License

BSD 3-Clause License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
