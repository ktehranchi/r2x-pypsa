# PyPSA → Sienna Validation

## Standard Workflow

The standard validation workflow consists of three steps:

```bash
# 1. Convert PyPSA to Sienna JSON and run PyPSA ED
uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch -v

# 2. Run Sienna Economic Dispatch (Julia)
julia tests/julia/run_sienna_ed.jl tests/test_output/test_network_1h_output_optimized.json tests/test_output/sienna_objective.txt

# 3. Compare objectives
uv run pytest tests/test_end_to_end.py::test_pypsa_sienna_objective_match -v
```

### Optional: System Capacity Comparison

Before running optimization, validate that system capacities match:

```bash
# Compare PyPSA and Sienna system capacities by category
uv run pytest tests/test_end_to_end.py::test_compare_pypsa_sienna_systems -v -s
```

This test:
- Converts PyPSA network to Sienna JSON (with caching)
- Compares generator capacities by category (thermal, renewable, hydro)
- Compares storage capacities
- Compares load metrics
- Outputs a detailed comparison table showing differences

### Optional: Visual Dispatch Comparison

After running steps 1-2, compare dispatch visually:

```bash
uv run python tests/tools/compare_dispatch_visual.py \
    --network tests/data/test_network_1h.nc \
    --pypsa-dispatch tests/test_output/pypsa_dispatch.csv \
    --sienna-dispatch tests/test_output/sienna_dispatch.csv \
    --sienna-json tests/test_output/test_network_1h_output_optimized.json
```

## Test Files

### `test_end_to_end.py`
End-to-end integration tests for PyPSA → Sienna conversion and validation.

- **`test_e2e_economic_dispatch`**:
  - Loads PyPSA network (`tests/data/test_network_1h.nc`), runs economic dispatch, saves dispatch CSV and objective
  - Converts PyPSA system to Sienna JSON format
  - Outputs: `pypsa_dispatch.csv`, `pypsa_objective.txt`, `test_network_1h_output_optimized.json`

- **`test_pypsa_sienna_objective_match`**:
  - Compares PyPSA and Sienna objective values (must match within 5%)
  - Reads objectives from files created by step 1 and 2

- **`test_end_to_end_pypsa_to_psy_conversion`**:
  - Tests basic PyPSA → PSY conversion without optimization

- **`test_compare_pypsa_sienna_systems`**:
  - Compares PyPSA and Sienna system metrics without running optimization
  - Validates that capacities match by category (thermal, renewable, hydro, storage)
  - Compares loads, generators, storage units, and buses
  - Uses caching to avoid regenerating JSON files if input hasn't changed
  - To force regeneration: `FORCE_REGENERATE=1 pytest tests/test_end_to_end.py::test_compare_pypsa_sienna_systems -v -s`

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

## Julia Scripts (`tests/julia/`)

### `run_sienna_ed.jl`
Julia script that runs Sienna Economic Dispatch on a converted JSON system.

- Loads Sienna system from JSON/H5 files
- Runs PowerSimulations Economic Dispatch
- Exports dispatch data to `sienna_dispatch.csv` and objective to text file
- Handles thermal, renewable, hydro, and storage generators

## Diagnostic Tools (`tests/tools/`)

Standalone scripts for debugging and analysis (not part of automated tests):

| Script | Description |
|--------|-------------|
| `compare_dispatch_visual.py` | Visual comparison of PyPSA vs Sienna dispatch with side-by-side plots |
| `compare_dispatch.py` | Detailed dispatch comparison by carrier |
| `compare_constraints_for_hour.py` | Hour-by-hour constraint analysis |
| `diagnose_dispatch_differences.py` | Analyze dispatch differences by generator |
| `diagnose_renewable_discrepancy.py` | Diagnose renewable generation discrepancies |
| `diagnose_time_series_differences.py` | Analyze time series data differences |
| `plot_renewable_totals.py` | Plot total renewable dispatch comparison |
| `plot_inter_area_flows.py` | Visualize inter-area power flows |

## Requirements

**Python**: pypsa, r2x, pytest, pandas, numpy, matplotlib
**Julia**: PowerSystems, PowerSimulations, Gurobi, CSV, DataFrames, TimeSeries

## Troubleshooting

**"Run test_e2e_economic_dispatch first"**
→ Generate JSON first: `uv run pytest tests/test_end_to_end.py::test_e2e_economic_dispatch`

**"Julia script failed"**
→ Check Julia packages: `julia --project=tests/julia -e 'using PowerSystems, PowerSimulations, Gurobi'`

**"KeyError: key 'compression_enabled' not found" when loading system in Julia**
→ The H5 file is missing compression attributes required by newer `InfrastructureSystems.jl`.
  This is a version mismatch between Python's H5 writer and Julia's reader.

  **Hotfix**: Add the missing attributes manually:

  ```julia
  using HDF5
  h5open("path/to/file.h5", "r+") do f
      ts_group = f["time_series"]
      HDF5.write_attribute(ts_group, "compression_enabled", false)
      HDF5.write_attribute(ts_group, "compression_type", "DEFLATE")
      HDF5.write_attribute(ts_group, "compression_level", 3)
      HDF5.write_attribute(ts_group, "compression_shuffle", true)
  end
  ```

  **Fixed in**: `src/r2x_pypsa/serialization/to_sienna.py` (lines 608-612).
  The H5 serialization now includes these compression attributes automatically.
