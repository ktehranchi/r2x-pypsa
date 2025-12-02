#!/usr/bin/env julia
# Load and prepare Sienna system (run once, then use run_sienna_ed_fast.jl)

# Activate local environment for reproducible package versions
import Pkg
Pkg.activate(@__DIR__)

using PowerSystems
using PowerSimulations
using PowerSimulations: ActivePowerTimeSeriesParameter
using Dates
using Serialization

const PSY = PowerSystems
const PSI = PowerSimulations

# Get JSON file path from command line arg
json_file = ARGS[1]
system_cache_file = ARGS[2]

println("Loading system from: $json_file")
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
    total_load = sum(get_max_active_power(l) for l in loads)
    println("  Total max load: $(total_load) MW")
    # Check individual loads
    for (i, l) in enumerate(loads[1:min(3, length(loads))])
        has_ts = has_time_series(l)
        static_max_pu = l.max_active_power
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
    total_thermal = sum(get_max_active_power(g) for g in thermal_gens)
    println("  Total thermal capacity: $(total_thermal) MW")
end
if !isempty(renewable_gens)
    total_renewable = sum(get_max_active_power(g) for g in renewable_gens)
    println("  Total renewable capacity: $(total_renewable) MW")
end

# Transform time series to DeterministicSingleTimeSeries (required for PowerSimulations v5)
println("Transforming time series...")
try
    transform_single_time_series!(sys, Hour(48), Hour(24))
    println("Transformed time series to DeterministicSingleTimeSeries")
catch e
    println("WARNING: Could not transform time series: $e")
end

# Create problem template
println("Creating problem template...")
template = ProblemTemplate()
set_device_model!(template, ThermalStandard, ThermalStandardDispatch)
set_device_model!(template, RenewableDispatch, RenewableFullDispatch)

# Configure StaticPowerLoad to use "active_power" time series
load_model = DeviceModel(
    PowerLoad, 
    StaticPowerLoad; 
    time_series_names = Dict(ActivePowerTimeSeriesParameter => "active_power")
)
set_device_model!(template, load_model)

# Check if HydroDispatch components exist and set model
if !isempty(collect(get_components(HydroDispatch, sys)))
    try
        set_device_model!(template, HydroDispatch, HydroDispatchRunOfRiver)
        println("Set HydroDispatch model: HydroDispatchRunOfRiver")
    catch e1
        try
            set_device_model!(template, HydroDispatch, PSI.HydroDispatchRunOfRiver)
            println("Set HydroDispatch model: PSI.HydroDispatchRunOfRiver")
        catch e2
            println("WARNING: Could not set HydroDispatch model - hydro will not be dispatched")
        end
    end
end

# Set storage device model
if !isempty(collect(get_components(EnergyReservoirStorage, sys)))
    try
        set_device_model!(template, EnergyReservoirStorage, PSI.EnergyReservoirManagement)
        println("Set EnergyReservoirStorage model: PSI.EnergyReservoirManagement")
    catch e1
        try
            set_device_model!(template, EnergyReservoirStorage, PSI.EnergyReservoirStorage)
            println("Set EnergyReservoirStorage model: PSI.EnergyReservoirStorage")
        catch e2
            println("WARNING: Could not set EnergyReservoirStorage model - storage will not be dispatched")
        end
    end
end

set_network_model!(template, NetworkModel(CopperPlatePowerModel))

# Save prepared system and template to cache file
println("Saving prepared system to: $system_cache_file")
serialize(system_cache_file, (sys, template))
println("✓ System prepared and cached!")

