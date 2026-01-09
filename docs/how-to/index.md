# How-To Guides

These guides provide step-by-step instructions for common tasks with r2x-pypsa.

## Available Guides

- **[Parsing Networks](parsing-networks.md)** - Different methods for loading and parsing PyPSA networks
- **[Converting Systems](converting-systems.md)** - Converting R2X systems to various output formats
- **[Validating Dispatch](validating-dispatch.md)** - Comparing PyPSA and Sienna economic dispatch results
- **[Running Sienna Simulations](running-sienna-simulations.md)** - Economic dispatch and resource adequacy in Sienna

## Quick Reference

### Parse a Network

```python
from r2x_pypsa.parser import PypsaParser

parser = PypsaParser(netcdf_file="network.nc")
system = parser.build_system()
```

### Convert to Sienna

```python
from r2x_pypsa.serialization import pypsa_to_sienna

pypsa_to_sienna(system, output_path="output/system")
```

### Run Validation

```bash
# PyPSA dispatch
uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch -v

# Sienna dispatch
julia tests/julia/run_sienna_ed.jl output/system.json output/sienna_objective.txt

# Compare
uv run pytest tests/test_end_to_end.py::test_pypsa_sienna_objective_match -v
```
