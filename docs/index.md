# r2x-pypsa

A PyPSA to Sienna converter and parser that enables interoperability between power system modeling platforms.

## What is r2x-pypsa?

r2x-pypsa is a bridge between [PyPSA](https://pypsa.org/) (Python for Power System Analysis) and [Sienna](https://www.nrel.gov/analysis/sienna.html) (Julia-based power system modeling framework). It enables:

- **Parse** PyPSA networks (NetCDF format) to R2X System objects
- **Convert** PyPSA components to PowerSystems.jl (Sienna) compatible format
- **Validate** economic dispatch results across modeling platforms

```{warning}
**Current Transmission Model Limitations**

r2x-pypsa currently only supports **zonal (AreaInterchange) transmission models**. PyPSA `Link` components are converted to Sienna `AreaInterchange` objects representing inter-area power transfer limits.

The following transmission models are **not yet supported**:
- AC transmission lines (`Line` → `ACBranch`)
- HVDC lines (`Link` with HVDC characteristics → `TwoTerminalHVDCLine`)

See the [Roadmap](#roadmap) section for planned features.
```

## Quick Example

```python
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna

# Load a PyPSA network and convert to R2X System
parser = PypsaParser(netcdf_file="network.nc")
system = parser.build_system()

# Convert to Sienna format
pypsa_to_sienna(system, output_path="sienna_system")
```

## Documentation Structure

```{toctree}
:maxdepth: 2
:caption: Getting Started

installation
```

```{toctree}
:maxdepth: 2
:caption: Tutorials

tutorials/index
tutorials/parsing-pypsa
tutorials/converting-to-sienna
```

```{toctree}
:maxdepth: 2
:caption: How-To Guides

how-to/index
how-to/parsing-networks
how-to/converting-systems
how-to/validating-dispatch
how-to/running-sienna-simulations
```

```{toctree}
:maxdepth: 2
:caption: Explanations

explanation/index
explanation/architecture
explanation/data-model
explanation/component-mapping
```

```{toctree}
:maxdepth: 2
:caption: Reference

reference/index
reference/api
```

## Roadmap

Planned features for future releases:

### Transmission Models

- [ ] AC transmission line support (`Line` → `ACBranch`)
- [ ] HVDC line support (`Link` → `TwoTerminalHVDCLine`)
- [ ] Multi-terminal HVDC networks

### Components

- [ ] Transformer support
- [ ] Shunt devices
- [ ] Series compensators

### Validation

- [ ] Unit commitment validation
- [ ] Multi-period optimization comparison
- [ ] Stochastic optimization support

## Related Projects

- [R2X](https://github.com/NREL/R2X) - The R2X framework for power system model translation
- [PyPSA](https://pypsa.org/) - Python for Power System Analysis
- [Sienna](https://www.nrel.gov/analysis/sienna.html) - Scalable Integrated Electric Network Analysis
- [PowerSystems.jl](https://github.com/NREL-Sienna/PowerSystems.jl) - Julia package for power system modeling

## License

BSD 3-Clause License
