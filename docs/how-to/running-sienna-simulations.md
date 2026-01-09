# Running Sienna Simulations

This guide covers how to run simulations in Sienna using systems converted from PyPSA.

## Overview

After converting a PyPSA network to Sienna format, you can run:
1. **Economic Dispatch** using PowerSimulations.jl
2. **Resource Adequacy Analysis** using SiennaPRASInterface

## Prerequisites

### Julia Packages

Install the required Julia packages:

```julia
using Pkg
Pkg.add([
    "PowerSystems",
    "PowerSimulations",
    "HydroPowerSimulations",
    "StorageSystemsSimulations",
    "SiennaPRASInterface",
    "HiGHS",  # or "Gurobi" for commercial solver
    "JuMP",
    "CSV",
    "DataFrames",
])
```

## Economic Dispatch Simulation

### Basic Example

Run a basic economic dispatch optimization:

```julia
using PowerSystems
using PowerSimulations
using HiGHS  # or Gurobi

# Load the converted system
sys = System("output/sienna_system.json")
set_units_base_system!(sys, "NATURAL_UNITS")

# Transform time series for PowerSimulations
transform_single_time_series!(sys, Hour(168), Hour(24))

# Create problem template
template = ProblemTemplate(NetworkModel(CopperPlatePowerModel))

# Set device models
set_device_model!(template, ThermalStandard, ThermalBasicDispatch)
set_device_model!(template, RenewableDispatch, RenewableFullDispatch)
set_device_model!(template, PowerLoad, StaticPowerLoad)
set_device_model!(template, EnergyReservoirStorage, BookKeepingwReservation)

# Build and solve the problem
problem = DecisionModel(template, sys;
    optimizer=optimizer_with_attributes(HiGHS.Optimizer),
    horizon=Hour(24),
)

build!(problem, output_dir="output/ed_results/")
solve!(problem)

# Get objective value
objective = objective_value(problem)
println("Objective value: \$$(round(objective, digits=2))")
```

### With Transmission Constraints

For network-constrained dispatch:

```julia
# Use DC power flow instead of copper plate
template = ProblemTemplate(NetworkModel(DCPPowerModel))

# Add line models
set_device_model!(template, Line, StaticBranch)
set_device_model!(template, MonitoredLine, StaticBranchBounds)

# Rebuild with network constraints
problem = DecisionModel(template, sys;
    optimizer=optimizer_with_attributes(HiGHS.Optimizer),
)
build!(problem, output_dir="output/ed_network/")
solve!(problem)
```

### Extracting Dispatch Results

Export generator dispatch to CSV:

```julia
using CSV
using DataFrames

# Get results from solved problem
results = get_results(problem)

# Extract generator dispatch
gen_dispatch = get_variable(results, :P__ThermalStandard)
renewable_dispatch = get_variable(results, :P__RenewableDispatch)

# Convert to DataFrame and save
df = DataFrame(gen_dispatch)
CSV.write("output/thermal_dispatch.csv", df)
```

## Resource Adequacy Analysis

### Basic PRAS Assessment

Run a Sequential Monte Carlo resource adequacy assessment:

```julia
using PowerSystems
using SiennaPRASInterface
using Statistics

const SPI = SiennaPRASInterface

# Load system
sys = System("output/sienna_system.json")
set_units_base_system!(sys, "NATURAL_UNITS")

# Define device models for RA assessment
device_models = [
    DeviceRAModel(ThermalStandard, GeneratorPRAS(max_active_power="max_active_power")),
    DeviceRAModel(HydroGen, GeneratorPRAS(max_active_power="max_active_power")),
    DeviceRAModel(RenewableGen, GeneratorPRAS(max_active_power="max_active_power")),
    DeviceRAModel(EnergyReservoirStorage, EnergyReservoirSoC()),
    DeviceRAModel(PowerLoad, StaticLoadPRAS(max_active_power="max_active_power")),
]

# Optionally add transmission if lines exist
lines = collect(get_components(Line, sys))
if length(lines) > 0
    push!(device_models, DeviceRAModel(Line, LinePRAS()))
    push!(device_models, DeviceRAModel(AreaInterchange, AreaInterchangeLimit()))
end

# Create RA template
problem_template = RATemplate(Area, device_models)

# Generate PRAS system
pras_sys = generate_pras_system(sys, problem_template)

# Run Monte Carlo assessment
method = SequentialMonteCarlo(
    samples=100,
    seed=42,
    verbose=true,
    threaded=false,
)

shortfalls, shortfall_stats = assess(pras_sys, method, ShortfallSamples(), Shortfall())

# Calculate reliability metrics
eue_result = EUE(shortfall_stats)
lole_result = LOLE(shortfall_stats)

println("Expected Unserved Energy (EUE): $(round(eue_result.eue.estimate, digits=2)) MWh/year")
println("Loss of Load Expectation (LOLE): $(round(lole_result.lole.estimate, digits=4)) hours/year")
```

### Analyzing Shortfall Events

Examine individual shortfall events:

```julia
# Get shortfall dimensions
n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

# Sum across regions for total system shortfall
total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)

# Calculate hourly statistics
mean_shortfall = vec(mean(total_shortfall, dims=2))
max_shortfall = vec(maximum(total_shortfall, dims=2))

# Find hours with shortfall
shortfall_hours = findall(mean_shortfall .> 0)
println("Hours with potential shortfall: $(length(shortfall_hours))")
```

### Exporting RA Results

Save results to CSV for further analysis:

```julia
using CSV
using DataFrames

# Summary statistics
summary_df = DataFrame(
    Metric = ["EUE (MWh/year)", "EUE Std Error", "LOLE (hours/year)", "LOLE Std Error"],
    Value = [
        eue_result.eue.estimate,
        eue_result.eue.standarderror,
        lole_result.lole.estimate,
        lole_result.lole.standarderror,
    ],
)
CSV.write("output/ra_summary.csv", summary_df)

# Hourly shortfall data
hourly_df = DataFrame(
    Hour = 1:n_timestamps,
    Mean_MW = mean_shortfall,
    Max_MW = max_shortfall,
)
CSV.write("output/hourly_shortfall.csv", hourly_df)
```

## Running from Command Line

### Economic Dispatch Script

```bash
julia --project=tests/julia tests/julia/run_sienna_ed.jl \
    output/sienna_system.json \
    output/sienna_objective.txt
```

### Resource Adequacy Script

```bash
cd tests/julia
julia --project=. test_resource_adequacy.jl
```

## Solver Configuration

### Using Gurobi (Commercial)

```julia
using Gurobi

problem = DecisionModel(template, sys;
    optimizer=optimizer_with_attributes(
        Gurobi.Optimizer,
        "MIPGap" => 0.01,
        "TimeLimit" => 3600,
    ),
)
```

### Using HiGHS (Open Source)

```julia
using HiGHS

problem = DecisionModel(template, sys;
    optimizer=optimizer_with_attributes(
        HiGHS.Optimizer,
        "time_limit" => 3600.0,
    ),
)
```

## Troubleshooting

### Time Series Not Found

If you get time series errors:
```julia
# Check what time series exist
for comp in get_components(Generator, sys)
    ts_keys = get_time_series_keys(comp)
    println("$(get_name(comp)): $(ts_keys)")
end
```

### Infeasible Problem

If the optimization is infeasible:
1. Check that loads don't exceed available generation
2. Verify transmission limits aren't too restrictive
3. Try relaxing ramp constraints initially

### PRAS System Generation Fails

Ensure components have required attributes:
```julia
# Check generators have forced outage rates
for gen in get_components(ThermalStandard, sys)
    println("$(get_name(gen)): FOR=$(get_forced_outage_rate(gen))")
end
```
