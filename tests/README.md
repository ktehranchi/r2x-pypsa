# PyPSA → Sienna Validation

## Standard Workflow

The standard validation workflow consists of three steps:

```bash
# 1. Convert PyPSA to Sienna JSON and run PyPSA ED
uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch -v

# 2. Run Sienna Economic Dispatch (Julia)
julia tests/run_sienna_ed.jl tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json tests/test_output/sienna_objective.txt

# 3. Compare objectives
uv run pytest tests/test_end_to_end.py::test_pypsa_sienna_objective_match -v
```

### Optional: Visual Dispatch Comparison

After running steps 1-2, compare dispatch visually:

```bash
uv run python tests/compare_dispatch_visual.py \
    --network tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc \
    --pypsa-dispatch tests/test_output/pypsa_dispatch.csv \
    --sienna-dispatch tests/test_output/sienna_dispatch.csv \
    --sienna-json tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json
```

## Test Files

### `test_end_to_end.py`
End-to-end integration tests for PyPSA → Sienna conversion and validation.

- **`test_e2e_economic_dispatch`**: 
  - Loads PyPSA network, runs economic dispatch, saves dispatch CSV and objective
  - Converts PyPSA system to Sienna JSON format
  - Outputs: `pypsa_dispatch.csv`, `pypsa_objective.txt`, `elec_s380_c7a_ec_lv1_output_optimized.json`

- **`test_pypsa_sienna_objective_match`**: 
  - Compares PyPSA and Sienna objective values (must match within 5%)
  - Reads objectives from files created by step 1 and 2

- **`test_end_to_end_pypsa_to_psy_conversion`**: 
  - Tests basic PyPSA → PSY conversion without optimization
  - Outputs: `elec_s380_c7a_ec_lv1_output.json`

### `run_sienna_ed.jl`
Julia script that runs Sienna Economic Dispatch on a converted JSON system.

- Loads Sienna system from JSON/H5 files
- Runs PowerSimulations Economic Dispatch
- Exports dispatch data to `sienna_dispatch.csv` and objective to text file
- Handles thermal, renewable, hydro, and storage generators

### `compare_dispatch_visual.py`
Visual comparison tool for PyPSA vs Sienna dispatch results.

- Generates side-by-side energy balance plots
- Compares marginal costs between systems
- Creates time series plots for dispatch comparison
- Outputs: `dispatch_comparison_energy_balance.png`, `dispatch_comparison_marginal_costs.png`

### `test_models.py`
Unit tests for PyPSA model components and time series conversion.

- Tests `PypsaGenerator` model creation and properties
- Tests time series conversion (`test_solar_time_series_conversion`)
- Tests capacity factor matching between PyPSA and Sienna (`test_solar_capacity_factors_match`)

### `test_parser.py`
Unit tests for PyPSA NetCDF parser functionality.

- Tests parser initialization and system building
- Tests component parsing (generators, buses, loads, storage, lines, links, stores)
- Tests attribute extraction and defaults
- Tests time-varying data handling

### `test_psy_serialization.py`
Unit tests for PowerSystems.jl serialization.

- Tests component serialization to JSON/H5 format
- Tests time series storage and retrieval

### `test_demo_parser.py`
Demo script for parsing a PyPSA network interactively.

- Useful for debugging and exploring parsed components
- Can be run with custom NetCDF files

## Requirements

**Python**: pypsa, r2x, pytest, pandas, numpy, matplotlib  
**Julia**: PowerSystems, PowerSimulations, Gurobi, CSV, DataFrames, TimeSeries

## Troubleshooting

**"Run test_e2e_economic_dispatch first"**  
→ Generate JSON first: `uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch`

**"Julia script failed"**  
→ Check Julia packages: `julia --project=tests -e 'using PowerSystems, PowerSimulations, Gurobi'`

**"Objectives differ by >5%"**  
→ Check time series loaded correctly in JSON, verify capacity factors match

**"File not found" errors**  
→ Ensure you've run `test_e2e_economic_dispatch` before running comparison tests
