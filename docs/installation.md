# Installation

This guide covers how to install r2x-pypsa and its dependencies.

## Prerequisites

- Python >= 3.11
- [uv](https://github.com/astral-sh/uv) package manager (recommended)

### Optional: Julia (for Sienna validation)

If you plan to run Sienna economic dispatch for validation, you'll also need:

- Julia >= 1.9
- PowerSystems.jl
- PowerSimulations.jl
- Gurobi.jl (or another supported solver)

## Installation Methods

### From Source (Recommended)

Clone the repository and install using uv:

```bash
git clone https://github.com/ktehranchi/r2x-pypsa.git
cd r2x-pypsa
uv sync
```

### Development Installation

For development work with editable installation:

```bash
git clone https://github.com/ktehranchi/r2x-pypsa.git
cd r2x-pypsa
uv sync --dev
```

## Dependencies

r2x-pypsa depends on the following packages:

| Package | Version | Description |
|---------|---------|-------------|
| pypsa | 0.35.2 | PyPSA power system analysis |
| r2x | latest | R2X framework |
| infrasys | >= 1.0.0 | Infrastructure system modeling |
| pandas | latest | Data manipulation |
| loguru | latest | Logging |
| gurobipy | >= 12.0.3 | Gurobi optimization solver |

## Verifying Installation

After installation, verify everything is working:

```python
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna

print("r2x-pypsa installed successfully!")
```

## Julia Setup (Optional)

For running Sienna economic dispatch validation, set up Julia:

```bash
# Install Julia packages
julia -e 'using Pkg; Pkg.add(["PowerSystems", "PowerSimulations", "Gurobi", "CSV", "DataFrames"])'
```

Or use the provided Project.toml:

```bash
cd tests/julia
julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

## Troubleshooting

### R2X Installation Issues

r2x-pypsa requires a specific branch of R2X. If you encounter issues:

```bash
uv pip install git+https://github.com/NREL/R2X@kt/v2_pre_r2xsienna
```

### Gurobi License

If you don't have a Gurobi license, you can use alternative solvers like HiGHS for smaller problems:

```bash
uv pip install highspy
```
