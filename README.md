# r2x-pypsa

PyPSA to R2X parser and converter for Sienna energy system modeling.

## Overview

`r2x-pypsa` is a Python package that enables conversion of PyPSA (Python for Power System Analysis) networks to Sienna-compatible JSON format. This allows PyPSA users to leverage Sienna's advanced power system simulation and optimization capabilities in Julia.

## Features

- **Parse PyPSA Networks**: Load PyPSA networks from NetCDF files
- **Convert to R2X Format**: Transform PyPSA components to R2X System format
- **Export to Sienna JSON**: Generate Sienna-compatible JSON files for use with PowerSystems.jl
- **Preserve Time Series**: Maintain all time-varying attributes from PyPSA networks
- **Flexible Mapping**: Customize component type mappings between PyPSA and Sienna

## Installation

```bash
# Using uv (recommended)
uv pip install r2x-pypsa

# Using pip
pip install r2x-pypsa
```

## Quick Start

```python
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping

# Parse PyPSA network
parser = PypsaParser(netcdf_file="path/to/network.nc")
system = parser.build_system()

# Convert to Sienna JSON
mapping = create_default_mapping()
pypsa_to_sienna(
    pypsa_system=system,
    output_path="output/sienna_system.json",
    mapping=mapping
)
```

## Documentation

- **[PyPSA to Sienna Conversion Guide](PYPSA_TO_SIENNA.md)**: Complete guide on converting PyPSA networks to Sienna JSON format
- **[Pydantic Patterns](PYDANTIC_PATTERNS.md)**: Internal development patterns and guidelines

## Supported Components

The parser handles the following PyPSA components:

- **Buses**: Network nodes with voltage levels
- **Generators**: Power generation units (thermal, renewable, storage)
- **Storage Units**: Energy storage with charge/discharge capabilities
- **Stores**: Simple energy storage containers
- **Links**: Bidirectional power connections
- **Lines**: AC transmission lines
- **Loads**: Power consumption

## Requirements

- Python >= 3.11
- PyPSA == 0.35.2
- R2X >= 1.1.0
- pandas
- loguru

## Examples

See the [conversion guide](PYPSA_TO_SIENNA.md) for detailed examples including:
- Basic conversion workflow
- Custom component mapping
- Batch conversion of multiple networks
- Working with time series data
- Troubleshooting common issues

## Testing

Run the test suite:

```bash
pytest tests/
```

Run the demo parser:

```bash
python tests/test_demo_parser.py --netcdf-file-path path/to/network.nc
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

See [LICENSE](LICENSE) file for details.