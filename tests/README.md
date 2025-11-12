# PyPSA → Sienna Validation

## Quick Start

```bash
# 1. Generate JSON from PyPSA (run once)
pytest tests/test_end_to_end.py::test_e2e_economic_dispatch -v

# 2. Validate PyPSA and Sienna match
pytest tests/test_end_to_end.py::test_pypsa_sienna_objective_match -v
```

## What It Does

`test_pypsa_sienna_objective_match`:
1. Runs PyPSA optimization → gets objective (~$42.2M)
2. Calls `run_sienna_ed.jl` → runs same problem in Sienna
3. Compares objectives (must match within 5%)

## Files

- `test_end_to_end.py` - Tests including validation
- `run_sienna_ed.jl` - Minimal Sienna ED runner
- `test_output/elec_s380_c7a_ec_lv1_output_optimized.json` - PyPSA → JSON conversion

## Requirements

**Python**: pypsa, r2x, pytest  
**Julia**: PowerSystems, PowerSimulations, Gurobi

## Troubleshooting

**"Run test_e2e_economic_dispatch first"**  
→ Generate JSON first: `pytest tests/test_end_to_end.py::test_e2e_economic_dispatch`

**"Julia script failed"**  
→ Check Julia packages: `julia -e 'using PowerSystems, PowerSimulations, Gurobi'`

**"Objectives differ by >5%"**  
→ Check time series loaded correctly in JSON

