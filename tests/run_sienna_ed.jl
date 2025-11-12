#!/usr/bin/env julia
# Run Sienna Economic Dispatch and return objective value

# Activate local environment for reproducible package versions
import Pkg
Pkg.activate(@__DIR__)

using PowerSystems
using PowerSimulations
using PowerSimulations: ActivePowerTimeSeriesParameter
using Gurobi
using Dates

const PSY = PowerSystems
const PSI = PowerSimulations

# Get JSON file path from command line arg
json_file = ARGS[1]
output_file = ARGS[2]

# Load system
sys = System(json_file)
set_units_base_system!(sys, "NATURAL_UNITS")

# Debug: Print system components
println("System components:")
println("  Buses: $(length(collect(get_components(ACBus, sys))))")
println("  PowerLoads: $(length(collect(get_components(PowerLoad, sys))))")
println("  ThermalStandard: $(length(collect(get_components(ThermalStandard, sys))))")
println("  RenewableDispatch: $(length(collect(get_components(RenewableDispatch, sys))))")

# Debug: Check load values
loads = collect(get_components(PowerLoad, sys))
if !isempty(loads)
    # get_max_active_power returns MW when using NATURAL_UNITS (static field in per-unit * base_power)
    total_load = sum(get_max_active_power(l) for l in loads)
    println("  Total max load: $(total_load) MW")
    # Check individual loads
    for (i, l) in enumerate(loads[1:min(3, length(loads))])
        # Check if time series exists
        has_ts = has_time_series(l)
        static_max_pu = l.max_active_power  # Direct field access
        get_max_pu = get_max_active_power(l)
        if has_ts
            ts_array = get_time_series_array(SingleTimeSeries, l, "active_power"; ignore_scaling_factors = true)
            ts_max_raw = maximum(values(ts_array))
            ts_array_scaled = get_time_series_array(SingleTimeSeries, l, "active_power"; ignore_scaling_factors = false)
            ts_max_scaled = maximum(values(ts_array_scaled))
            println("    Load $(i): $(get_name(l))")
            println("      base=$(get_base_power(l)), static_max_pu=$(static_max_pu), get_max_pu=$(get_max_pu)")
            println("      has_ts=$(has_ts), ts_max_raw=$(ts_max_raw), ts_max_scaled=$(ts_max_scaled)")
        else
            println("    Load $(i): $(get_name(l)), base=$(get_base_power(l)), static_max_pu=$(static_max_pu), get_max_pu=$(get_max_pu) MW")
        end
    end
end

# Debug: Check generation capacity
thermal_gens = collect(get_components(ThermalStandard, sys))
renewable_gens = collect(get_components(RenewableDispatch, sys))
if !isempty(thermal_gens)
    total_thermal = sum(get_max_active_power(g) * get_base_power(g) for g in thermal_gens)
    println("  Total thermal capacity: $(total_thermal) MW")
end
if !isempty(renewable_gens)
    total_renewable = sum(get_max_active_power(g) * get_base_power(g) for g in renewable_gens)
    println("  Total renewable capacity: $(total_renewable) MW")
end

# DEBUG: Uncomment to exit early and skip slow optimization
# exit(0)

# Transform time series to DeterministicSingleTimeSeries (required for PowerSimulations v5)
# This converts SingleTimeSeries to DeterministicSingleTimeSeries with forecast horizon
try
    transform_single_time_series!(sys, Hour(48), Hour(24))
    println("Transformed time series to DeterministicSingleTimeSeries")
catch e
    println("WARNING: Could not transform time series: $e")
end

# Create problem template
template = ProblemTemplate()
set_device_model!(template, ThermalStandard, ThermalStandardDispatch)
set_device_model!(template, RenewableDispatch, RenewableFullDispatch)
# Configure StaticPowerLoad to use "active_power" time series (not "max_active_power") to avoid PowerSystems v5 bug
# where get_max_active_power() returns MW instead of per-unit when a time series named "max_active_power" exists
load_model = DeviceModel(
    PowerLoad, 
    StaticPowerLoad; 
    time_series_names = Dict(ActivePowerTimeSeriesParameter => "active_power")
)
set_device_model!(template, load_model)

# Check if HydroDispatch components exist and set model
# Note: PowerSimulations v5 API may differ from v4
if !isempty(collect(get_components(HydroDispatch, sys)))
    try
        # Try v4 API name first
        set_device_model!(template, HydroDispatch, HydroDispatchRunOfRiver)
        println("Set HydroDispatch model: HydroDispatchRunOfRiver")
    catch e1
        try
            # Try with PSI prefix
            set_device_model!(template, HydroDispatch, PSI.HydroDispatchRunOfRiver)
            println("Set HydroDispatch model: PSI.HydroDispatchRunOfRiver")
        catch e2
            println("WARNING: Could not set HydroDispatch model - hydro will not be dispatched")
            println("  Error 1: $e1")
            println("  Error 2: $e2")
        end
    end
end

# Set storage device model (PowerSimulations v5 API)
if !isempty(collect(get_components(EnergyReservoirStorage, sys)))
    try
        # Try v5 API - storage models may have different names
        set_device_model!(template, EnergyReservoirStorage, PSI.EnergyReservoirManagement)
        println("Set EnergyReservoirStorage model: PSI.EnergyReservoirManagement")
    catch e1
        try
            # Alternative v5 API name
            set_device_model!(template, EnergyReservoirStorage, PSI.EnergyReservoirStorage)
            println("Set EnergyReservoirStorage model: PSI.EnergyReservoirStorage")
        catch e2
            println("WARNING: Could not set EnergyReservoirStorage model - storage will not be dispatched")
            println("  Error 1: $e1")
            println("  Error 2: $e2")
        end
    end
end

set_network_model!(template, NetworkModel(CopperPlatePowerModel))

# Create and solve model
# Specify resolution to avoid "multiple resolutions" error
# All time series should be hourly (Hour(1))
model = DecisionModel(
    template,
    sys;
    name = "ED",
    optimizer = optimizer_with_attributes(
        Gurobi.Optimizer, 
        "OutputFlag" => 1,  # Enable output to see infeasibility details
        "LogToConsole" => 1,
    ),
    system_to_file = false,
    resolution = Hour(1),  # Explicitly set resolution to Hour(1)
    initialize_model = false,  # Skip initial conditions to avoid initialization failure
)

# build! requires output_dir in PowerSimulations v5
output_dir = mktempdir()
build!(model; output_dir=output_dir)
solve!(model)

# Get objective
results = OptimizationProblemResults(model)
objective = get_objective_value(results)

# Write objective to file
open(output_file, "w") do f
    write(f, string(objective))
end

println(objective)

