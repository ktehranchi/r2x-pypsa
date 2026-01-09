# Validating Dispatch Results

This guide covers how to validate that PyPSA and Sienna produce equivalent economic dispatch results.

## Overview

The validation workflow compares objective values from PyPSA and Sienna economic dispatch:

1. Run PyPSA economic dispatch and convert to Sienna format
2. Run Sienna economic dispatch
3. Compare objective values

## Prerequisites

- Python environment with r2x-pypsa installed
- Julia with PowerSystems.jl and PowerSimulations.jl
- Gurobi solver (or compatible alternative)

## Step 1: PyPSA Dispatch and Conversion

Run PyPSA economic dispatch and convert to Sienna:

```bash
uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch -v
```

This test:
- Loads the PyPSA network from `tests/data/test_network_1h.nc`
- Runs PyPSA economic dispatch
- Saves dispatch results to `tests/test_output/pypsa_dispatch.csv`
- Saves objective value to `tests/test_output/pypsa_objective.txt`
- Converts to Sienna JSON format

## Step 2: Sienna Economic Dispatch

Run the Sienna economic dispatch:

```bash
julia tests/julia/run_sienna_ed.jl \
    tests/test_output/test_network_1h_output_optimized.json \
    tests/test_output/sienna_objective.txt
```

This Julia script:
- Loads the converted Sienna system
- Runs economic dispatch using PowerSimulations.jl
- Saves dispatch results to `tests/test_output/sienna_dispatch.csv`
- Saves objective value to `tests/test_output/sienna_objective.txt`

## Step 3: Compare Results

Compare the objective values:

```bash
uv run pytest tests/test_end_to_end.py::test_pypsa_sienna_objective_match -v
```

This test reads both objective files and verifies they match within a 5% tolerance.

## Optional: System Comparison

Before running optimization, validate system capacities:

```bash
uv run pytest tests/test_end_to_end.py::test_compare_pypsa_sienna_systems -v -s
```

This compares:
- Generator capacities by category (thermal, renewable, hydro)
- Storage capacities
- Load totals
- Bus counts

## Optional: Visual Dispatch Comparison

Compare dispatch visually:

```bash
uv run python tests/tools/compare_dispatch_visual.py \
    --network tests/data/test_network_1h.nc \
    --pypsa-dispatch tests/test_output/pypsa_dispatch.csv \
    --sienna-dispatch tests/test_output/sienna_dispatch.csv \
    --sienna-json tests/test_output/test_network_1h_output_optimized.json
```

## Diagnostic Tools

Additional diagnostic scripts in `tests/tools/`:

| Script | Purpose |
|--------|---------|
| `compare_dispatch.py` | Detailed dispatch comparison by carrier |
| `compare_constraints_for_hour.py` | Hour-by-hour constraint analysis |
| `diagnose_dispatch_differences.py` | Analyze differences by generator |
| `diagnose_renewable_discrepancy.py` | Diagnose renewable generation issues |
| `diagnose_time_series_differences.py` | Analyze time series data differences |

## Troubleshooting

### Objective Values Don't Match

1. Check system capacities match: run `test_compare_pypsa_sienna_systems`
2. Check time series alignment: verify `p_max_pu` time series are identical
3. Compare dispatch by carrier: use `compare_dispatch.py`

### Julia Script Fails

Verify Julia packages are installed:

```bash
julia --project=tests/julia -e 'using PowerSystems, PowerSimulations, Gurobi'
```

### Missing Output Files

Run tests in order - Step 1 must complete before Step 2 or 3:

```bash
uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch -v
```
