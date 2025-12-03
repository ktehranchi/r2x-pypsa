#!/usr/bin/env julia
# Run Sienna Economic Dispatch and return objective value
# 
# Usage:
#   julia run_sienna_ed.jl <json_file> <output_file>
# 
# Automatically uses cache if available and newer than JSON file for faster iteration.

# Activate local environment for reproducible package versions
# Note: Can also use `julia --project=tests` flag to activate before script runs
import Pkg
Pkg.activate(@__DIR__)

using PowerSystems
using PowerSystems: get_time_series_array, DeterministicSingleTimeSeries, PrimeMovers
using PowerSimulations
using PowerSimulations: ActivePowerTimeSeriesParameter, ActivePowerVariable, ActivePowerOutVariable, ActivePowerInVariable
using Gurobi
using Dates
using Serialization
using TimeSeries
using CSV
using DataFrames
using Printf
using Statistics

# Import hydro and storage dispatch formulations
# These require separate packages: HydroPowerSimulations.jl and StorageSystemsSimulations.jl
has_hydro_pkg = false
has_storage_pkg = false

try
    using HydroPowerSimulations
    global has_hydro_pkg = true
    println("✓ HydroPowerSimulations.jl loaded successfully")
catch e
    global has_hydro_pkg = false
    @warn "HydroPowerSimulations.jl not available - hydro dispatch will be disabled"
    println("  Error: $e")
end

try
    using StorageSystemsSimulations
    global has_storage_pkg = true
    println("✓ StorageSystemsSimulations.jl loaded successfully")
catch e
    global has_storage_pkg = false
    @warn "StorageSystemsSimulations.jl not available - storage dispatch will be disabled"
    println("  Error: $e")
end

const PSY = PowerSystems
const PSI = PowerSimulations

# Get JSON file path from command line arg (or use defaults if running in REPL)
if length(ARGS) >= 2
    json_file = ARGS[1]
    output_file = ARGS[2]
else
    # Default paths for REPL usage
    json_file = "test_output/elec_s380_c7a_ec_lv1_output_optimized.json"
    output_file = "test_output/sienna_objective.txt"
    println("Using default paths (run with args for custom paths):")
    println("  JSON: $json_file")
    println("  Output: $output_file")
end

# Check if we can use cached system (faster)
system_cache_file = replace(json_file, ".json" => "_system_cache.jls")
use_cache = false

if isfile(system_cache_file) && isfile(json_file)
    cache_mtime = mtime(system_cache_file)
    json_mtime = mtime(json_file)
    if cache_mtime > json_mtime
        use_cache = true
        println("Using cached system (cache is newer than JSON file)")
        println("  Cache: $system_cache_file (modified: $(Dates.unix2datetime(cache_mtime)))")
        println("  JSON: $json_file (modified: $(Dates.unix2datetime(json_mtime)))")
    else
        println("Cache is older than JSON file, will reload system")
    end
end

# Load system (use cache if available and newer than JSON)
# NOTE: We can't cache the System object because it contains SQLite connections that don't serialize well
# So we always load from JSON, but we can cache the template
if use_cache
    println("Loading system from JSON and cached template...")
    sys = System(json_file)
    set_units_base_system!(sys, "NATURAL_UNITS")
    
    # Transform time series (required even when using cached template)
    # Use 1 week (168 hours) to match PyPSA optimization period
    println("Transforming time series...")
    try
        transform_single_time_series!(sys, Hour(7*24), Hour(24))
        println("Transformed time series to DeterministicSingleTimeSeries (1 week horizon)")
    catch e
        println("WARNING: Could not transform time series: $e")
    end
    
    # Verify time series alignment (same verification as below)
    println("\nVerifying time series alignment...")
    try
        using PowerSystems: get_time_series_keys, get_time_series_array, get_time_series, DeterministicSingleTimeSeries, get_resolution
        
        # Collect all time series from all components
        all_ts_info = []
        component_types = [PowerLoad, ThermalStandard, RenewableDispatch, EnergyReservoirStorage]
        
        for comp_type in component_types
            components = collect(get_components(comp_type, sys))
            for comp in components
                ts_keys = get_time_series_keys(comp)
                for key in ts_keys
                    try
                        # Get the time series object (not the array)
                        ts_obj = get_time_series(DeterministicSingleTimeSeries, comp, key.name)
                        if ts_obj !== nothing
                            # Get the array for length and data checks
                            ts_data = get_time_series_array(DeterministicSingleTimeSeries, comp, key.name)
                            if ts_data !== nothing && !isempty(ts_data)
                                # Get resolution from the time series object
                                ts_resolution = get_resolution(ts_obj)
                                # Get timestamps from the array (TimeArray has timestamps)
                                ts_timestamps = TimeSeries.timestamp(ts_data)
                                push!(all_ts_info, (
                                    component_type = string(comp_type),
                                    component_name = get_name(comp),
                                    ts_name = key.name,
                                    length = length(ts_data),
                                    resolution = ts_resolution,
                                    initial_time = first(ts_timestamps),
                                    final_time = last(ts_timestamps),
                                    has_nan = any(isnan.(TimeSeries.values(ts_data))),
                                    has_inf = any(isinf.(TimeSeries.values(ts_data))),
                                ))
                            end
                        end
                    catch e
                        # Silently skip time series that can't be retrieved (e.g., invalid time series names for certain component types)
                        # Only print warnings for unexpected errors
                        if !occursin("not implemented", string(e)) && !occursin("not found", string(e))
                            println("  WARNING: Could not get time series $(key.name) for $(get_name(comp)): $e")
                        end
                    end
                end
            end
        end
        
        if isempty(all_ts_info)
            println("  WARNING: No time series found in system!")
        else
            # Check alignment
            lengths = [ts.length for ts in all_ts_info]
            resolutions = [ts.resolution for ts in all_ts_info]
            initial_times = [ts.initial_time for ts in all_ts_info]
            
            unique_lengths = unique(lengths)
            unique_resolutions = unique(resolutions)
            unique_initial_times = unique(initial_times)
            
            println("  Time series summary:")
            println("    Total time series: $(length(all_ts_info))")
            println("    Unique lengths: $(unique_lengths)")
            println("    Unique resolutions: $(unique_resolutions)")
            println("    Unique initial times: $(length(unique_initial_times))")
            
            # Check for alignment issues
            issues = []
            if length(unique_lengths) > 1
                push!(issues, "MISMATCH: Time series have different lengths: $(unique_lengths)")
            end
            if length(unique_resolutions) > 1
                push!(issues, "MISMATCH: Time series have different resolutions: $(unique_resolutions)")
            end
            if length(unique_initial_times) > 1
                push!(issues, "MISMATCH: Time series have different initial times: $(unique_initial_times[1:min(3, length(unique_initial_times))])...")
            end
            
            # Check for NaN/Inf values
            nan_ts = [ts for ts in all_ts_info if ts.has_nan]
            inf_ts = [ts for ts in all_ts_info if ts.has_inf]
            
            if !isempty(nan_ts)
                push!(issues, "INVALID: $(length(nan_ts)) time series contain NaN values")
                for ts in nan_ts[1:min(3, length(nan_ts))]
                    println("    - $(ts.component_type).$(ts.component_name).$(ts.ts_name)")
                end
            end
            if !isempty(inf_ts)
                push!(issues, "INVALID: $(length(inf_ts)) time series contain Inf values")
                for ts in inf_ts[1:min(3, length(inf_ts))]
                    println("    - $(ts.component_type).$(ts.component_name).$(ts.ts_name)")
                end
            end
            
            if isempty(issues)
                println("  ✓ All time series are aligned and valid")
            else
                println("  ✗ Time series alignment issues found:")
                for issue in issues
                    println("    $issue")
                end
            end
            
            # Show sample of time series by component type
            println("\n  Sample time series by component type:")
            for comp_type in unique([ts.component_type for ts in all_ts_info])
                type_ts = [ts for ts in all_ts_info if ts.component_type == comp_type]
                if !isempty(type_ts)
                    sample = type_ts[1]
                    println("    $(comp_type): $(length(type_ts)) time series, length=$(sample.length), resolution=$(sample.resolution)")
                end
            end
        end
    catch e
        println("  ERROR: Could not verify time series alignment: $e")
        println("  Stacktrace:")
        for (exc, bt) in Base.catch_stack()
            showerror(stdout, exc, bt)
            println()
        end
    end
    
    # Load cached template
    cached_data = Serialization.deserialize(system_cache_file)
    if cached_data isa Tuple && length(cached_data) == 2
        # Old format: (sys, template) - ignore sys, use template
        _, template = cached_data
    else
        # New format: just template
        template = cached_data
    end
    println("✓ Loaded system from JSON and template from cache")
else
    println("Loading system from JSON (this may take a while)...")
    sys = System(json_file)
    set_units_base_system!(sys, "NATURAL_UNITS")
    
    # Transform time series to DeterministicSingleTimeSeries (required for PowerSimulations v5)
    # This converts SingleTimeSeries to DeterministicSingleTimeSeries with forecast horizon
    # Use 1 week (168 hours) to match PyPSA optimization period
    println("Transforming time series...")
    try
        transform_single_time_series!(sys, Hour(7*24), Hour(24))
        println("Transformed time series to DeterministicSingleTimeSeries (1 week horizon)")
    catch e
        println("WARNING: Could not transform time series: $e")
    end

    # Verify time series alignment
    println("\nVerifying time series alignment...")
    try
        using PowerSystems: get_time_series_keys, get_time_series_array, get_time_series, DeterministicSingleTimeSeries, get_resolution
        
        # Collect all time series from all components
        all_ts_info = []
        component_types = [PowerLoad, ThermalStandard, RenewableDispatch, EnergyReservoirStorage]
        
        for comp_type in component_types
            components = collect(get_components(comp_type, sys))
            for comp in components
                ts_keys = get_time_series_keys(comp)
                for key in ts_keys
                    try
                        # Get the time series object (not the array)
                        ts_obj = get_time_series(DeterministicSingleTimeSeries, comp, key.name)
                        if ts_obj !== nothing
                            # Get the array for length and data checks
                            ts_data = get_time_series_array(DeterministicSingleTimeSeries, comp, key.name)
                            if ts_data !== nothing && !isempty(ts_data)
                                # Get resolution from the time series object
                                ts_resolution = get_resolution(ts_obj)
                                # Get timestamps from the array (TimeArray has timestamps)
                                ts_timestamps = TimeSeries.timestamp(ts_data)
                                push!(all_ts_info, (
                                    component_type = string(comp_type),
                                    component_name = get_name(comp),
                                    ts_name = key.name,
                                    length = length(ts_data),
                                    resolution = ts_resolution,
                                    initial_time = first(ts_timestamps),
                                    final_time = last(ts_timestamps),
                                    has_nan = any(isnan.(TimeSeries.values(ts_data))),
                                    has_inf = any(isinf.(TimeSeries.values(ts_data))),
                                ))
                            end
                        end
                    catch e
                        # Silently skip time series that can't be retrieved (e.g., invalid time series names for certain component types)
                        # Only print warnings for unexpected errors
                        if !occursin("not implemented", string(e)) && !occursin("not found", string(e))
                            println("  WARNING: Could not get time series $(key.name) for $(get_name(comp)): $e")
                        end
                    end
                end
            end
        end
        
        if isempty(all_ts_info)
            println("  WARNING: No time series found in system!")
        else
            # Check alignment
            lengths = [ts.length for ts in all_ts_info]
            resolutions = [ts.resolution for ts in all_ts_info]
            initial_times = [ts.initial_time for ts in all_ts_info]
            
            unique_lengths = unique(lengths)
            unique_resolutions = unique(resolutions)
            unique_initial_times = unique(initial_times)
            
            println("  Time series summary:")
            println("    Total time series: $(length(all_ts_info))")
            println("    Unique lengths: $(unique_lengths)")
            println("    Unique resolutions: $(unique_resolutions)")
            println("    Unique initial times: $(length(unique_initial_times))")
            
            # Check for alignment issues
            issues = []
            if length(unique_lengths) > 1
                push!(issues, "MISMATCH: Time series have different lengths: $(unique_lengths)")
            end
            if length(unique_resolutions) > 1
                push!(issues, "MISMATCH: Time series have different resolutions: $(unique_resolutions)")
            end
            if length(unique_initial_times) > 1
                push!(issues, "MISMATCH: Time series have different initial times: $(unique_initial_times[1:min(3, length(unique_initial_times))])...")
            end
            
            # Check for NaN/Inf values
            nan_ts = [ts for ts in all_ts_info if ts.has_nan]
            inf_ts = [ts for ts in all_ts_info if ts.has_inf]
            
            if !isempty(nan_ts)
                push!(issues, "INVALID: $(length(nan_ts)) time series contain NaN values")
                for ts in nan_ts[1:min(3, length(nan_ts))]
                    println("    - $(ts.component_type).$(ts.component_name).$(ts.ts_name)")
                end
            end
            if !isempty(inf_ts)
                push!(issues, "INVALID: $(length(inf_ts)) time series contain Inf values")
                for ts in inf_ts[1:min(3, length(inf_ts))]
                    println("    - $(ts.component_type).$(ts.component_name).$(ts.ts_name)")
                end
            end
            
            if isempty(issues)
                println("  ✓ All time series are aligned and valid")
            else
                println("  ✗ Time series alignment issues found:")
                for issue in issues
                    println("    $issue")
                end
            end
            
            # Show sample of time series by component type
            println("\n  Sample time series by component type:")
            for comp_type in unique([ts.component_type for ts in all_ts_info])
                type_ts = [ts for ts in all_ts_info if ts.component_type == comp_type]
                if !isempty(type_ts)
                    sample = type_ts[1]
                    println("    $(comp_type): $(length(type_ts)) time series, length=$(sample.length), resolution=$(sample.resolution)")
                end
            end
        end
    catch e
        println("  ERROR: Could not verify time series alignment: $e")
        println("  Stacktrace:")
        for (exc, bt) in Base.catch_stack()
            showerror(stdout, exc, bt)
            println()
        end
    end

    # Create problem template
    println("Creating problem template...")
    template = ProblemTemplate()
    set_device_model!(template, ThermalStandard, ThermalStandardDispatch)
    set_device_model!(template, RenewableDispatch, RenewableFullDispatch)
    
    # Debug: Check wind generator marginal costs
    println("\nDebug: Wind generator marginal costs:")
    local renewable_gens = collect(get_components(RenewableDispatch, sys))
    local wind_gens = [g for g in renewable_gens if get_prime_mover_type(g) in [PrimeMovers.WT, PrimeMovers.WS]]
    
    wind_marginal_costs = Float64[]
    wind_zero_cost_count = 0
    wind_nonzero_cost_count = 0
    
    for gen in wind_gens[1:min(10, length(wind_gens))]  # Check first 10
        gen_name = get_name(gen)
        try
            op_cost = get_operation_cost(gen)
            if op_cost !== nothing
                # For RenewableGenerationCost, get variable cost
                var_cost = get_variable(op_cost)
                if var_cost !== nothing
                    value_curve = get_value_curve(var_cost)
                    if value_curve !== nothing
                        # Check if it's a LinearCurve (marginal cost is proportional_term)
                        if isa(value_curve, PowerSystems.LinearCurve)
                            mc = get_proportional_term(value_curve)
                            push!(wind_marginal_costs, mc)
                            if abs(mc) < 1e-6
                                wind_zero_cost_count += 1
                                println("  $gen_name: marginal_cost = $mc \$/MWh (zero)")
                            else
                                wind_nonzero_cost_count += 1
                                println("  $gen_name: marginal_cost = $mc \$/MWh ⚠️  NON-ZERO!")
                            end
                        else
                            println("  $gen_name: value_curve is $(typeof(value_curve)), not LinearCurve")
                        end
                    else
                        println("  $gen_name: value_curve is nothing")
                    end
                else
                    println("  $gen_name: no variable cost")
                end
            else
                println("  $gen_name: no operation_cost")
            end
        catch e
            println("  $gen_name: error getting operation_cost - $e")
        end
    end
    
    # Summary of marginal costs
    if !isempty(wind_marginal_costs)
        println("\n  Wind marginal cost summary (first $(min(10, length(wind_gens))) generators):")
        println("    Zero cost: $wind_zero_cost_count")
        println("    Non-zero cost: $wind_nonzero_cost_count")
        if wind_nonzero_cost_count > 0
            println("    ⚠️  WARNING: Some wind generators have non-zero marginal costs!")
            println("    This could explain why wind is not being fully dispatched.")
            println("    Non-zero costs: $(wind_marginal_costs[wind_marginal_costs .!= 0.0])")
        end
        println("    Cost range: [$(round(minimum(wind_marginal_costs), digits=6)), $(round(maximum(wind_marginal_costs), digits=6))] \$/MWh")
    end
    
    # Configure StaticPowerLoad - use default "max_active_power" time series name
    # Note: There was a PowerSystems v5 bug where get_max_active_power() returns MW instead of per-unit
    # when a time series named "max_active_power" exists, but this may have been fixed or the workaround
    # using "active_power" may be causing scaling issues. Reverting to default to test.
    set_device_model!(template, PowerLoad, StaticPowerLoad)

    # Set storage device model
    if !isempty(collect(get_components(EnergyReservoirStorage, sys)))
        if has_storage_pkg
            try
                # Use StorageDispatchWithReserves from StorageSystemsSimulations.jl
                storage_model = DeviceModel(
                    EnergyReservoirStorage,
                    StorageSystemsSimulations.StorageDispatchWithReserves;
                    attributes = Dict{String, Any}(
                        "reservation" => false,
                        "cycling_limits" => false,
                        "energy_target" => false,
                        "complete_coverage" => false,
                        "regularization" => false,
                    ),
                )
                set_device_model!(template, storage_model)
                println("✓ Set EnergyReservoirStorage model: StorageDispatchWithReserves (dispatchable)")
            catch e
                println("WARNING: Could not set EnergyReservoirStorage model with StorageDispatchWithReserves")
                println("  Error: $e")
                # Fallback to FixedOutput
                try
                    storage_model = DeviceModel(EnergyReservoirStorage, FixedOutput)
                    set_device_model!(template, storage_model)
                    println("  Fallback: Using FixedOutput for EnergyReservoirStorage (not dispatchable)")
                catch e2
                    println("  Fallback also failed: $e2")
                end
            end
        else
            println("WARNING: EnergyReservoirStorage components found but StorageSystemsSimulations.jl not available")
            println("  Storage will not be dispatched. Add StorageSystemsSimulations.jl to Project.toml")
        end
    end

    # Set network model (no slack variables for pure economic dispatch)
    set_network_model!(template, NetworkModel(CopperPlatePowerModel))
    
    # Save template to cache for next time (don't cache system - it has SQLite connections)
    println("Saving template to cache: $system_cache_file")
    Serialization.serialize(system_cache_file, template)
    println("✓ Cached template for faster future runs")
end

# Debug: Print system components (always run, regardless of cache)
println("\nSystem components:")
println("  Buses: $(length(collect(get_components(ACBus, sys))))")
println("  PowerLoads: $(length(collect(get_components(PowerLoad, sys))))")
println("  ThermalStandard: $(length(collect(get_components(ThermalStandard, sys))))")
println("  RenewableDispatch: $(length(collect(get_components(RenewableDispatch, sys)))) (includes hydro)")
println("  EnergyReservoirStorage: $(length(collect(get_components(EnergyReservoirStorage, sys))))")

# Debug: Check load values
loads = collect(get_components(PowerLoad, sys))
if !isempty(loads)
    # get_max_active_power returns MW when using NATURAL_UNITS (static field in per-unit * base_power)
    total_load = sum(get_max_active_power(l) for l in loads)
    println("  Total max load: $(total_load) MW")
end

# Debug: Check generation capacity
# NOTE: get_max_active_power() with NATURAL_UNITS already returns MW (per-unit * base_power)
# So we should NOT multiply by get_base_power() again
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

# Check storage (hydro is now included in RenewableDispatch)
storage_units = collect(get_components(EnergyReservoirStorage, sys))

# Check hydro (filter from RenewableDispatch by prime_mover_type)
hydro_gens = [g for g in collect(get_components(RenewableDispatch, sys)) if get_prime_mover_type(g) == PrimeMovers.HY]
if !isempty(hydro_gens)
    total_hydro = sum(get_max_active_power(g) for g in hydro_gens)
    println("  Total hydro capacity: $(total_hydro) MW")
end
if !isempty(storage_units)
    # For storage, we need to check input/output limits
    # get_input_active_power_limits/get_output_active_power_limits return MW when NATURAL_UNITS is set
    local total_storage = 0.0
    for s in storage_units
        input_limits = get_input_active_power_limits(s)
        output_limits = get_output_active_power_limits(s)
        total_storage += max(input_limits.max, output_limits.max)
    end
    println("  Total storage capacity: $(total_storage) MW")
    
    # Check storage initial conditions
    println("\nChecking storage initial conditions...")
    for s in storage_units[1:min(5, length(storage_units))]  # Check first 5
        try
            initial_soc = get_initial_storage_capacity_level(s)
            storage_cap = get_storage_capacity(s)
            initial_energy = initial_soc * storage_cap
            println("  $(get_name(s)): initial SOC=$(round(initial_soc, digits=3)), capacity=$(round(storage_cap, digits=2)) MWh, initial energy=$(round(initial_energy, digits=2)) MWh")
        catch e
            println("  $(get_name(s)): Could not get initial conditions: $e")
        end
    end
end

# ===== SIENNA SYSTEM CAPACITY COMPARISON TABLE =====
println("\n" * "="^80)
println("SIENNA SYSTEM METRICS")
println("="^80)

# Collect all components
loads = collect(get_components(PowerLoad, sys))
thermal_gens = collect(get_components(ThermalStandard, sys))
all_renewable_gens = collect(get_components(RenewableDispatch, sys))
storage_units = collect(get_components(EnergyReservoirStorage, sys))
buses = collect(get_components(ACBus, sys))

# Filter renewable generators by prime mover type
solar_gens = [g for g in all_renewable_gens if get_prime_mover_type(g) == PrimeMovers.PVe]
wind_gens = [g for g in all_renewable_gens if get_prime_mover_type(g) in [PrimeMovers.WT, PrimeMovers.WS]]
hydro_gens = [g for g in all_renewable_gens if get_prime_mover_type(g) == PrimeMovers.HY]
# Renewable excluding hydro
renewable_gens_excl_hydro = [g for g in all_renewable_gens if get_prime_mover_type(g) != PrimeMovers.HY]

# Calculate metrics
load_count = length(loads)
total_max_load = isempty(loads) ? 0.0 : sum(get_max_active_power(l) for l in loads)
peak_load = isempty(loads) ? 0.0 : maximum(get_max_active_power(l) for l in loads)

solar_count = length(solar_gens)
wind_count = length(wind_gens)
hydro_count = length(hydro_gens)
thermal_count = length(thermal_gens)
total_generators = thermal_count + length(all_renewable_gens)

thermal_capacity = isempty(thermal_gens) ? 0.0 : sum(get_max_active_power(g) for g in thermal_gens)
renewable_capacity = isempty(renewable_gens_excl_hydro) ? 0.0 : sum(get_max_active_power(g) for g in renewable_gens_excl_hydro)
hydro_capacity = isempty(hydro_gens) ? 0.0 : sum(get_max_active_power(g) for g in hydro_gens)
total_capacity = thermal_capacity + renewable_capacity + hydro_capacity

storage_count = length(storage_units)
storage_capacity = if !isempty(storage_units)
    local total = 0.0
    for s in storage_units
        input_limits = get_input_active_power_limits(s)
        output_limits = get_output_active_power_limits(s)
        total += max(input_limits.max, output_limits.max)
    end
    total
else
    0.0
end

bus_count = length(buses)

# Print formatted table
println("\n" * " " ^ 30 * "Metric" * " " ^ 20 * "Sienna")
println("-" ^ 80)

# Helper function for formatting
function format_metric(name::String, value::Union{Int, Float64, String})
    if value isa Float64
        value_str = @sprintf("%.2f", value)
    else
        value_str = string(value)
    end
    println(lpad(name, 50) * " | " * rpad(value_str, 20))
end

format_metric("Load Count", load_count)
format_metric("Total Max Load (MW)", total_max_load)
format_metric("Peak Load (MW)", peak_load)
format_metric("Solar Generators", solar_count)
format_metric("Wind Generators", wind_count)
format_metric("Hydro Generators", hydro_count)
format_metric("Total Generators", total_generators)
format_metric("Thermal Generators", thermal_count)
format_metric("Thermal Capacity (MW)", thermal_capacity)
format_metric("Renewable Generators (RenewableDispatch)", length(all_renewable_gens))
format_metric("Renewable Capacity (MW)", renewable_capacity)
format_metric("Hydro Generators (HydroDispatch)", hydro_count)
format_metric("Hydro Capacity (MW)", hydro_capacity)
format_metric("Total Generation Capacity (MW)", total_capacity)
format_metric("Storage Units", storage_count)
format_metric("Storage Capacity (MW)", storage_capacity)
format_metric("Buses", bus_count)

println("="^80)

# DEBUG: Check load vs generation at specific time steps (especially time step 5 where conflict occurs)
println("\nChecking load vs generation capacity at key time steps...")
try
    # Get time series data for loads and generators
    local loads = collect(get_components(PowerLoad, sys))
    local thermal_gens = collect(get_components(ThermalStandard, sys))
    local renewable_gens = collect(get_components(RenewableDispatch, sys))  # Includes hydro generators
    local storage_units = collect(get_components(EnergyReservoirStorage, sys))
    
    # Get time series for a few time steps (0-indexed, so step 5 = index 5)
    time_steps_to_check = [1, 5, 10, 24]  # Check a few time steps including the problematic one
    
    for step in time_steps_to_check
        local total_load = 0.0
        local total_thermal_available = 0.0
        local total_renewable_available = 0.0
        local total_hydro_available = 0.0
        local total_thermal_min = 0.0  # Track minimum generation requirements
        
        # Sum loads at this time step
        # Compare with working code: it uses get_max_active_power() which returns MW
        # For time step, we need actual load at that time, not max
        # Time series are stored in per-unit (0-1), multiply by max_active_power to get MW
        for load in loads
            try
                ts_data = get_time_series_array(DeterministicSingleTimeSeries, load, "max_active_power")
                if ts_data !== nothing && length(ts_data) > step
                    ts_value = TimeSeries.values(ts_data)[step]
                    # Time series is in per-unit (0-1), multiply by max_active_power to get MW
                    max_load = get_max_active_power(load)  # Already in MW with NATURAL_UNITS
                    load_val = abs(ts_value) * max_load
                    total_load += load_val
                else
                    # No time series, use static max (same as working code)
                    total_load += get_max_active_power(load)
                end
            catch
                # Use static value if no time series (same as working code)
                total_load += get_max_active_power(load)
            end
        end
        
        # Sum available generation capacity at this time step
        # Use same pattern as working code: get_max_active_power() already returns MW
        for gen in thermal_gens
            # Use static max capacity (same as working code)
            total_thermal_available += get_max_active_power(gen)
            
            # Check minimum generation requirement
            try
                min_limits = get_active_power_limits(gen)
                total_thermal_min += min_limits.min  # Already in MW with NATURAL_UNITS
            catch
                # No minimum constraint
            end
        end
        
        for gen in renewable_gens
            # For renewable, check if time series limits availability at this time step
            max_cap = get_max_active_power(gen)  # Already in MW
            try
                ts_data = get_time_series_array(DeterministicSingleTimeSeries, gen, "max_active_power")
                if ts_data !== nothing && length(ts_data) > step
                    # Time series is capacity factor (per-unit 0-1), multiply by nameplate
                    capacity_factor = TimeSeries.values(ts_data)[step]
                    if 0.0 <= capacity_factor <= 1.0  # Sanity check
                        total_renewable_available += capacity_factor * max_cap
                    else
                        total_renewable_available += max_cap
                    end
                else
                    total_renewable_available += max_cap
                end
            catch
                total_renewable_available += max_cap
            end
        end
        
        for gen in hydro_gens
            total_hydro_available += get_max_active_power(gen)
        end
        
        total_available = total_thermal_available + total_renewable_available + total_hydro_available
        
        println("  Time step $step:")
        println("    Load: $(round(total_load, digits=2)) MW")
        println("    Available generation: $(round(total_available, digits=2)) MW")
        println("      - Thermal: $(round(total_thermal_available, digits=2)) MW (min required: $(round(total_thermal_min, digits=2)) MW)")
        println("      - Renewable: $(round(total_renewable_available, digits=2)) MW")
        println("      - Hydro: $(round(total_hydro_available, digits=2)) MW")
        println("    Balance: $(round(total_available - total_load, digits=2)) MW")
        
        if total_load > total_available
            println("    ⚠️  WARNING: Load exceeds available generation!")
        end
        
        # Check if minimum generation exceeds load
        if total_thermal_min > total_load
            println("    ⚠️  WARNING: Minimum thermal generation ($(round(total_thermal_min, digits=2)) MW) exceeds load!")
        end
    end
catch e
    println("  Could not check load vs generation: $e")
end

# DEBUG: Uncomment to exit early and skip slow optimization
# exit(0)

# Create and solve model
# Specify resolution to avoid "multiple resolutions" error
# All time series should be hourly (Hour(1))
# Use the forecast horizon from the system (should be 1 week = 168 hours after transformation)
println("\nCreating optimization model...")
# Get the actual forecast horizon from the system (should match what we set in transform_single_time_series!)
forecast_horizon = get_forecast_horizon(sys)
println("  System forecast horizon: $(forecast_horizon)")
println("  Expected: 168 hours (1 week)")

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
    horizon = forecast_horizon,  # Use the forecast horizon from the system (should be 168 hours)
    initialize_model = false,  # Skip initial conditions to avoid initialization failure
    calculate_conflict = true,  # Enable conflict calculation to identify infeasible constraints
    store_variable_names = true,  # Store variable names for better debugging
)

# Check what components are in the model
println("\nChecking model components:")
try
    # Try to get component counts from the model (may not be available until build!)
    println("  Model created successfully")
catch e
    println("  Could not inspect model before build: $e")
end

# build! requires output_dir in PowerSimulations v5
println("Building model...")
output_dir = mktempdir()
build!(model; output_dir=output_dir)

# Check what's actually in the built model
println("\nModel built. Checking dispatched components:")
try
    # Try to get component information from the built model
    # This is PowerSimulations-specific and may vary by version
    println("  Model built successfully")
    # Note: Component counts may not be directly accessible, but we can check the template
    # Template uses Symbol keys (e.g., :ThermalStandard, not ThermalStandard type)
    println("  Template device models:")
    println("    Available device model keys: $(keys(template.devices))")
    println("    - ThermalStandard: $(haskey(template.devices, :ThermalStandard))")
    println("    - RenewableDispatch: $(haskey(template.devices, :RenewableDispatch))")
    println("    - PowerLoad: $(haskey(template.devices, :PowerLoad))")
    # Note: Hydro generators are now included in RenewableDispatch
    if haskey(template.devices, :EnergyReservoirStorage)
        println("    - EnergyReservoirStorage: ✓ (in template)")
    else
        println("    - EnergyReservoirStorage: ✗ (NOT in template - will not be dispatched)")
    end
catch e
    println("  Could not inspect model: $e")
end

println("\nSolving model...")
global objective = nothing
global results = nothing
try
    solve!(model)
    
    # Get objective
    global results = OptimizationProblemResults(model)
    global objective = get_objective_value(results)
    println("✓ Model solved successfully!")
    println("  Objective: $(objective)")
    
    # Debug: Comprehensive wind dispatch and capacity analysis
    println("\n" * "="^80)
    println("WIND DISPATCH DEBUGGING")
    println("="^80)
    try
        using PowerSimulations: read_variable, TableFormat
        local renewable_gens = collect(get_components(RenewableDispatch, sys))
        local wind_gens = [g for g in renewable_gens if get_prime_mover_type(g) in [PrimeMovers.WT, PrimeMovers.WS]]
        
        println("\nTotal wind generators: $(length(wind_gens))")
        
        renewable_df = read_variable(results, ActivePowerVariable, RenewableDispatch, table_format=TableFormat.LONG)
        if !isempty(renewable_df)
            first_ts = renewable_df.DateTime[1]
            println("Analyzing time step: $first_ts")
            
            # Per-generator debugging
            println("\n" * "-"^80)
            println("PER-GENERATOR DETAILS (first 10 generators):")
            println("-"^80)
            println(lpad("Generator", 30), " | ", 
                    rpad("Base Power", 12), " | ",
                    rpad("Rating", 8), " | ",
                    rpad("PF", 6), " | ",
                    rpad("Max Active", 12), " | ",
                    rpad("TS Value", 12), " | ",
                    rpad("TS Range?", 10), " | ",
                    rpad("Avail (CF*BP)", 15), " | ",
                    rpad("Avail (CF*Max)", 15), " | ",
                    rpad("Dispatch", 12), " | ",
                    rpad("Util %", 8), " | ",
                    rpad("Marg Cost", 10))
            println("-"^80)
            
            wind_dispatch_ts1 = 0.0
            wind_available_ts1_base = 0.0
            wind_available_ts1_max = 0.0
            total_base_power = 0.0
            ts_values_all = Float64[]
            ts_values_gt_one = 0
            generators_with_ts = 0
            
            for (idx, gen) in enumerate(wind_gens[1:min(10, length(wind_gens))])
                gen_name = get_name(gen)
                base_power = get_base_power(gen)
                rating = get_rating(gen)
                power_factor = get_power_factor(gen)
                max_active = get_max_active_power(gen)
                total_base_power += base_power
                
                # Get dispatch
                dispatch_val = 0.0
                gen_rows = filter(row -> row.name == gen_name && row.DateTime == first_ts, renewable_df)
                if !isempty(gen_rows)
                    dispatch_val = gen_rows.value[1]
                    wind_dispatch_ts1 += dispatch_val
                end
                
                # Get available (from time series) - try both methods
                available_base = 0.0
                available_max = 0.0
                ts_value_raw = nothing
                ts_in_range = "?"
                ts_data = nothing  # Declare outside try block for use in debugging
                
                try
                    ts_data = get_time_series_array(DeterministicSingleTimeSeries, gen, "max_active_power")
                    if ts_data !== nothing && length(ts_data) >= 1
                        generators_with_ts += 1
                        ts_values = TimeSeries.values(ts_data)
                        ts_value_raw = ts_values[1]
                        push!(ts_values_all, ts_value_raw)
                        
                        # Check if time series is in per-unit range (0-1)
                        ts_min = minimum(ts_values)
                        ts_max = maximum(ts_values)
                        ts_mean = mean(ts_values)
                        
                        if ts_max > 1.0
                            ts_in_range = "NO (>1.0)"
                            ts_values_gt_one += 1
                            # If > 1.0, might be in MW - check if it matches base_power
                            if abs(ts_max - base_power) < 0.01 * base_power
                                ts_in_range = "MW (match)"
                            end
                        elseif ts_max <= 1.0 && ts_min >= 0.0
                            ts_in_range = "YES (0-1)"
                        else
                            ts_in_range = "NO (<0)"
                        end
                        
                        # Method 1: capacity_factor * base_power
                        available_base = ts_value_raw * base_power
                        wind_available_ts1_base += available_base
                        
                        # Method 2: capacity_factor * get_max_active_power() (matches line 683 pattern)
                        available_max = ts_value_raw * max_active
                        wind_available_ts1_max += available_max
                    else
                        ts_in_range = "NO TS"
                    end
                catch e
                    ts_in_range = "ERROR"
                end
                
                utilization = available_base > 0 ? (dispatch_val / available_base * 100) : 0.0
                
                # Get marginal cost
                marginal_cost_str = "N/A"
                marginal_cost_val = nothing
                try
                    op_cost = get_operation_cost(gen)
                    if op_cost !== nothing
                        var_cost = get_variable(op_cost)
                        if var_cost !== nothing
                            value_curve = get_value_curve(var_cost)
                            if value_curve !== nothing && isa(value_curve, PowerSystems.LinearCurve)
                                mc = get_proportional_term(value_curve)
                                marginal_cost_val = mc
                                marginal_cost_str = @sprintf("%.4f", mc)
                            end
                        end
                    end
                catch
                    marginal_cost_str = "ERROR"
                end
                
                println(lpad(gen_name, 30), " | ",
                        rpad(@sprintf("%.2f", base_power), 12), " | ",
                        rpad(@sprintf("%.3f", rating), 8), " | ",
                        rpad(@sprintf("%.3f", power_factor), 6), " | ",
                        rpad(@sprintf("%.2f", max_active), 12), " | ",
                        rpad(ts_value_raw !== nothing ? @sprintf("%.6f", ts_value_raw) : "N/A", 12), " | ",
                        rpad(ts_in_range, 10), " | ",
                        rpad(@sprintf("%.2f", available_base), 15), " | ",
                        rpad(@sprintf("%.2f", available_max), 15), " | ",
                        rpad(@sprintf("%.2f", dispatch_val), 12), " | ",
                        rpad(@sprintf("%.1f", utilization), 8), " | ",
                        rpad(marginal_cost_str, 10))
                
                # Debug zero dispatch cases
                if dispatch_val == 0.0 && ts_value_raw !== nothing && ts_value_raw > 0.0
                    println("    ⚠️  WARNING: $gen_name has TS value $(ts_value_raw) but dispatch is 0.00")
                    
                    # Check generator availability
                    try
                        is_available = get_available(gen)
                        println("      Generator available: $is_available")
                    catch
                        println("      Generator available: (could not check)")
                    end
                    
                    # Check if TS value at timestep 1 is actually 0
                    if ts_data !== nothing && length(ts_data) >= 1
                        ts_values_full = TimeSeries.values(ts_data)
                        ts_timestamps = TimeSeries.timestamp(ts_data)
                        println("      TS value at timestep 1: $(ts_values_full[1])")
                        if length(ts_values_full) > 1
                            println("      TS value at timestep 2: $(ts_values_full[2])")
                        end
                        println("      TS min/max across all timesteps: $(minimum(ts_values_full)) / $(maximum(ts_values_full))")
                        
                        # Check if timestep 1 TS is actually 0
                        if abs(ts_values_full[1]) < 1e-6
                            println("      ✓ TS value at timestep 1 is ~0.0 - explains zero dispatch")
                        else
                            println("      ⚠️  TS value at timestep 1 is NOT 0.0 - dispatch should be > 0")
                            if marginal_cost_val !== nothing
                                println("      Marginal cost: $(marginal_cost_val) \$/MWh")
                                if abs(marginal_cost_val) > 1e-6
                                    println("      ⚠️  Generator has non-zero marginal cost - may explain low dispatch")
                                end
                            end
                        end
                    end
                end
            end
            
            # Summary statistics
            println("\n" * "-"^80)
            println("SUMMARY STATISTICS:")
            println("-"^80)
            println("  Total wind generators: $(length(wind_gens))")
            println("  Generators with time series: $generators_with_ts")
            println("  Total base_power (nameplate): $(round(sum(get_base_power(g) for g in wind_gens), digits=2)) MW")
            
            if !isempty(ts_values_all)
                println("  Time series value statistics:")
                println("    Min: $(round(minimum(ts_values_all), digits=6))")
                println("    Max: $(round(maximum(ts_values_all), digits=6))")
                println("    Mean: $(round(mean(ts_values_all), digits=6))")
                println("    Median: $(round(median(ts_values_all), digits=6))")
                println("  Generators with TS values > 1.0: $ts_values_gt_one")
                if ts_values_gt_one > 0
                    println("    ⚠️  WARNING: Time series values > 1.0 detected!")
                    println("    This suggests time series might be in MW, not per-unit (0-1)")
                end
            end
            
            println("\n  Time step 1 (first timestep) totals:")
            println("    Wind dispatched: $(round(wind_dispatch_ts1, digits=2)) MW")
            println("    Wind available (method 1: CF * base_power): $(round(wind_available_ts1_base, digits=2)) MW")
            println("    Wind available (method 2: CF * get_max_active_power()): $(round(wind_available_ts1_max, digits=2)) MW")
            
            if wind_available_ts1_base > 0
                utilization_base = wind_dispatch_ts1 / wind_available_ts1_base * 100
                println("    Wind utilization (method 1): $(round(utilization_base, digits=1))%")
            end
            if wind_available_ts1_max > 0
                utilization_max = wind_dispatch_ts1 / wind_available_ts1_max * 100
                println("    Wind utilization (method 2): $(round(utilization_max, digits=1))%")
            end
            
            # Compare with working code pattern (from lines 674-689)
            println("\n  Comparison with working code pattern (from load vs generation check):")
            try
                local renewable_gens_check = collect(get_components(RenewableDispatch, sys))
                local wind_gens_check = [g for g in renewable_gens_check if get_prime_mover_type(g) in [PrimeMovers.WT, PrimeMovers.WS]]
                local total_renewable_available_check = 0.0
                for gen in wind_gens_check
                    max_cap = get_max_active_power(gen)
                    try
                        ts_data = get_time_series_array(DeterministicSingleTimeSeries, gen, "max_active_power")
                        if ts_data !== nothing && length(ts_data) > 0
                            capacity_factor = TimeSeries.values(ts_data)[1]
                            if 0.0 <= capacity_factor <= 1.0
                                total_renewable_available_check += capacity_factor * max_cap
                            else
                                total_renewable_available_check += max_cap
                            end
                        else
                            total_renewable_available_check += max_cap
                        end
                    catch
                        total_renewable_available_check += max_cap
                    end
                end
                println("    Wind available (working pattern: CF * get_max_active_power()): $(round(total_renewable_available_check, digits=2)) MW")
                if total_renewable_available_check > 0
                    utilization_working = wind_dispatch_ts1 / total_renewable_available_check * 100
                    println("    Wind utilization (working pattern): $(round(utilization_working, digits=1))%")
                end
            catch e
                println("    Could not calculate using working pattern: $e")
            end
            
            # Check optimizer constraints (what the optimizer actually sees)
            println("\n  Optimizer constraint inspection:")
            try
                using PowerSimulations: read_parameter, ActivePowerTimeSeriesParameter
                # Try to read the parameter values that the optimizer uses
                # These should match the time series constraints
                param_key = ActivePowerTimeSeriesParameter()
                try
                    param_df = read_parameter(results, param_key, RenewableDispatch, table_format=TableFormat.LONG)
                    if !isempty(param_df)
                        # Filter to wind generators and first timestep
                        wind_param_df = filter(row -> begin
                            gen = get_component(RenewableDispatch, sys, row.name)
                            pm = get_prime_mover_type(gen)
                            pm in [PrimeMovers.WT, PrimeMovers.WS]
                        end && row.DateTime == first_ts, param_df)
                        
                        if !isempty(wind_param_df)
                            total_param_upper_bound = sum(wind_param_df.value)
                            println("    Wind parameter upper bounds (from optimizer): $(round(total_param_upper_bound, digits=2)) MW")
                            println("    This is what the optimizer sees as the constraint limit")
                            println("    Compare with calculated available: $(round(wind_available_ts1_base, digits=2)) MW (method 1)")
                            println("    Compare with calculated available: $(round(wind_available_ts1_max, digits=2)) MW (method 2)")
                            
                            if total_param_upper_bound > 0
                                param_utilization = wind_dispatch_ts1 / total_param_upper_bound * 100
                                println("    Wind utilization (vs optimizer constraint): $(round(param_utilization, digits=1))%")
                            end
                        else
                            println("    Could not find wind generator parameters in optimizer results")
                        end
                    else
                        println("    No parameter data found in results")
                    end
                catch e2
                    println("    Could not read parameter values: $e2")
                    println("    (This is expected if parameters are not stored in results)")
                end
            catch e
                println("    Could not inspect optimizer constraints: $e")
            end
        end
        println("="^80)
    catch e
        println("  Could not check wind dispatch: $e")
        println("  Stacktrace:")
        for (exc, bt) in Base.catch_stack()
            showerror(stdout, exc, bt)
            println()
        end
    end
catch e
    println("  ✗ Model solve failed: $e")
    println("  The issue is likely a constraint violation (e.g., power balance, storage, hydro, or ramp constraints).")
    println("  Check:")
    println("    - Power balance (supply vs demand)")
    println("    - Storage initial conditions and energy limits")
    println("    - Hydro water availability constraints")
    println("    - Ramp rate constraints")
    rethrow(e)
end

# Write objective to file (only if solve was successful)
if objective !== nothing
    open(output_file, "w") do f
        write(f, string(objective))
    end
    println("\nObjective written to: $output_file")
    
    # Export dispatch data grouped by carrier for plotting
    try
        using PowerSimulations: read_variable, TableFormat
        
        # Create dispatch file in same directory as output_file
        dispatch_file = joinpath(dirname(output_file), "sienna_dispatch.csv")
        println("\nExporting dispatch data to: $dispatch_file")
        
        # Collect dispatch data from all generator types
        dispatch_data = DataFrame()
        
        # Thermal generators
        try
            thermal_df = read_variable(results, ActivePowerVariable, ThermalStandard, table_format=TableFormat.LONG)
            if !isempty(thermal_df)
                # Get carrier (fuel type) for each thermal generator
                for row in eachrow(thermal_df)
                    gen = get_component(ThermalStandard, sys, row.name)
                    carrier = string(get_fuel(gen))
                    push!(dispatch_data, (DateTime=row.DateTime, name=row.name, carrier=carrier, value=row.value))
                end
            end
        catch e
            println("  Could not read thermal dispatch: $e")
        end
        
        # Renewable generators
        try
            renewable_df = read_variable(results, ActivePowerVariable, RenewableDispatch, table_format=TableFormat.LONG)
            if !isempty(renewable_df)
                for row in eachrow(renewable_df)
                    gen = get_component(RenewableDispatch, sys, row.name)
                    # Use prime mover type as carrier (e.g., "WT" for wind, "PVe" for solar)
                    carrier = string(get_prime_mover_type(gen))
                    push!(dispatch_data, (DateTime=row.DateTime, name=row.name, carrier=carrier, value=row.value))
                end
            end
        catch e
            println("  Could not read renewable dispatch: $e")
        end
        
        # Hydro generators are now included in RenewableDispatch
        # They will be handled by the renewable dispatch section above
        # If you need to separate hydro from other renewables, filter by prime_mover_type == PrimeMovers.HY
        
        # Storage units (use ActivePowerOutVariable for discharge, ActivePowerInVariable for charge)
        try
            # Discharge (positive values)
            storage_out_df = read_variable(results, ActivePowerOutVariable, EnergyReservoirStorage, table_format=TableFormat.LONG)
            if !isempty(storage_out_df)
                for row in eachrow(storage_out_df)
                    if row.value > 0  # Only positive discharge
                        carrier = "battery"
                        push!(dispatch_data, (DateTime=row.DateTime, name=row.name, carrier=carrier, value=row.value))
                    end
                end
            end
            # Charge (negative values - stored as positive in ActivePowerInVariable)
            storage_in_df = read_variable(results, ActivePowerInVariable, EnergyReservoirStorage, table_format=TableFormat.LONG)
            if !isempty(storage_in_df)
                for row in eachrow(storage_in_df)
                    if row.value > 0  # Charge is positive in ActivePowerInVariable, but represents negative supply
                        carrier = "battery"
                        push!(dispatch_data, (DateTime=row.DateTime, name=row.name, carrier=carrier, value=-row.value))  # Negative for charging
                    end
                end
            end
        catch e
            println("  Could not read storage dispatch: $e")
        end
        
        # Loads (read from time series - loads are parameters, not optimization variables)
        # Sum all loads per timestamp to get total system load
        try
            local loads = collect(get_components(PowerLoad, sys))
            if !isempty(loads)
                # Get time range from dispatch_data if available, otherwise from first load's time series
                time_range = nothing
                if !isempty(dispatch_data) && hasproperty(dispatch_data, :DateTime)
                    time_range = unique(dispatch_data.DateTime)
                else
                    # Get time range from first load's time series
                    for load in loads
                        try
                            ts_data = get_time_series_array(DeterministicSingleTimeSeries, load, "max_active_power")
                            if ts_data !== nothing
                                time_range = TimeSeries.timestamp(ts_data)
                                break
                            end
                        catch
                            continue
                        end
                    end
                end
                
                if time_range !== nothing
                    # Create a dictionary to sum loads per timestamp
                    load_by_time = Dict{DateTime, Float64}()
                    for ts_time in time_range
                        load_by_time[ts_time] = 0.0
                    end
                    
                    # Sum all loads at each timestamp
                    for load in loads
                        try
                            # Get load time series data
                            ts_data = get_time_series_array(DeterministicSingleTimeSeries, load, "max_active_power")
                            max_load = get_max_active_power(load)  # Already in MW with NATURAL_UNITS
                            
                            if ts_data !== nothing
                                ts_values = TimeSeries.values(ts_data)
                                ts_timestamps = TimeSeries.timestamp(ts_data)
                                
                                # Add this load's contribution to each timestamp
                                for (i, ts_time) in enumerate(ts_timestamps)
                                    if ts_time in keys(load_by_time)
                                        # Time series is in per-unit (0-1), multiply by max_load to get MW
                                        load_value = abs(ts_values[i]) * max_load
                                        load_by_time[ts_time] += load_value
                                    end
                                end
                            else
                                # No time series, use static max load for all time steps
                                for ts_time in time_range
                                    if ts_time in keys(load_by_time)
                                        load_by_time[ts_time] += max_load
                                    end
                                end
                            end
                        catch e2
                            # Skip this load if there's an error
                            continue
                        end
                    end
                    
                    # Add summed load data to dispatch_data (one entry per timestamp)
                    carrier = "load"
                    for (ts_time, total_load) in load_by_time
                        push!(dispatch_data, (DateTime=ts_time, name="total_load", carrier=carrier, value=total_load))
                    end
                end
            end
        catch e
            println("  Could not read load data: $e")
        end
        
        if !isempty(dispatch_data)
            CSV.write(dispatch_file, dispatch_data)
            println("✓ Dispatch data exported to: $dispatch_file")
        else
            println("  ⚠️  No dispatch data collected")
        end
    catch e
        println("  Could not export dispatch data: $e")
        println("  Stacktrace:")
        for (exc, bt) in Base.catch_stack()
            showerror(stdout, exc, bt)
            println()
        end
    end
    
    # ============================================================================
    # HYDRO DISPATCH DIAGNOSTIC COMPARISON
    # ============================================================================
    # Hydro generators are now included in RenewableDispatch (not HydroDispatch)
    # Find them by filtering RenewableDispatch components with prime_mover_type == PrimeMovers.HY
    local all_renewable = collect(get_components(RenewableDispatch, sys))
    println("\nDebug: Total RenewableDispatch components: $(length(all_renewable))")
    
    # Check prime mover types
    if !isempty(all_renewable)
        prime_mover_counts = Dict()
        for gen in all_renewable
            pm = get_prime_mover_type(gen)
            prime_mover_counts[pm] = get(prime_mover_counts, pm, 0) + 1
        end
        println("  Prime mover types in RenewableDispatch:")
        for (pm, count) in prime_mover_counts
            println("    $pm: $count")
        end
    end
    
    local hydro_gens = [g for g in all_renewable if get_prime_mover_type(g) == PrimeMovers.HY]
    println("  Hydro generators (PrimeMovers.HY): $(length(hydro_gens))")
    
    if isempty(hydro_gens)
        println("\nNo hydro generators found in system (hydro is now mapped to RenewableDispatch)")
        println("Skipping hydro diagnostic section.")
    else
        println("\n" * "="^80)
        println("HYDRO DISPATCH DIAGNOSTIC COMPARISON")
        println("="^80)
        
        # Declare hydro_df in outer scope so it's available throughout
        local hydro_df = DataFrame(DateTime=[], name=[], value=[])
        
        try
            using PowerSimulations: read_variable, TableFormat
            println("\nHydro Generator Details:")
            println("-"^80)
            println(lpad("Generator Name", 25), " | ", 
                    rpad("Capacity (MW)", 15), " | ",
                    rpad("TS Max (MW)", 15), " | ",
                    rpad("Sienna Total (MWh)", 18), " | ",
                    rpad("Sienna Max (MW)", 15), " | ",
                    rpad("Sienna Avg (MW)", 15), " | ",
                    rpad("Zero Timesteps", 15))
            println("-"^80)
            
            # Hydro generators are now included in RenewableDispatch
            # Filter renewable dispatch to get only hydro generators (prime_mover_type == PrimeMovers.HY)
            try
                using PowerSimulations: read_variable, TableFormat
                renewable_df = read_variable(results, ActivePowerVariable, RenewableDispatch, table_format=TableFormat.LONG)
                if !isempty(renewable_df) && hasproperty(renewable_df, :name) && hasproperty(renewable_df, :DateTime) && hasproperty(renewable_df, :value)
                    # Filter to only hydro generators
                    hydro_dispatch_rows = []
                    for row in eachrow(renewable_df)
                        try
                            gen = get_component(RenewableDispatch, sys, row.name)
                            if get_prime_mover_type(gen) == PrimeMovers.HY
                                push!(hydro_dispatch_rows, (DateTime=row.DateTime, name=row.name, value=row.value))
                            end
                        catch e2
                            # Skip if generator not found or other error
                            continue
                        end
                    end
                    hydro_df = isempty(hydro_dispatch_rows) ? DataFrame(DateTime=[], name=[], value=[]) : DataFrame(hydro_dispatch_rows)
                else
                    hydro_df = DataFrame(DateTime=[], name=[], value=[])
                end
            catch e
                println("  Could not read hydro dispatch: $e")
                println("  Stacktrace:")
                for (exc, bt) in Base.catch_stack()
                    showerror(stdout, exc, bt)
                    println()
                end
                hydro_df = DataFrame(DateTime=[], name=[], value=[])
            end
            
            # Create summary DataFrame
            hydro_summary = DataFrame(
                name = String[],
                capacity_mw = Float64[],
                ts_max_mw = Float64[],
                sienna_total_mwh = Float64[],
                sienna_max_mw = Float64[],
                sienna_avg_mw = Float64[],
                zero_timesteps = Int[],
                utilization_pct = Float64[]
            )
            
            for gen in hydro_gens
                gen_name = get_name(gen)
                
                # Get capacity - use base_power which is the nameplate capacity in MW
                base_power = get_base_power(gen)  # This is in MW (nameplate capacity)
                
                # For RenewableDispatch, get_max_active_power() returns MW (with NATURAL_UNITS)
                # It accounts for time series if present
                max_active_power = get_max_active_power(gen)  # MW
                
                # Get time series max (if available)
                # For RenewableDispatch, the time series is in per-unit (0-1)
                ts_max_mw = max_active_power  # Default to max_active_power if no time series
                try
                    ts_data = get_time_series_array(DeterministicSingleTimeSeries, gen, "max_active_power")
                    if ts_data !== nothing
                        ts_values = TimeSeries.values(ts_data)
                        # Time series is stored in per-unit (0-1), multiply by base_power to get MW
                        # Note: get_max_active_power() already accounts for time series, but we want the max of the time series
                        ts_max_pu = maximum(ts_values)
                        ts_max_mw = ts_max_pu * base_power  # Convert per-unit to MW
                    end
                catch
                    # No time series or error - use max_active_power as default
                    ts_max_mw = max_active_power
                end
                
                # Get dispatch for this generator
                gen_dispatch = if !isempty(hydro_df) && hasproperty(hydro_df, :name) && hasproperty(hydro_df, :value)
                    filter(row -> row.name == gen_name, hydro_df)
                else
                    DataFrame(DateTime=[], name=[], value=[])
                end
                
                if !isempty(gen_dispatch) && hasproperty(gen_dispatch, :value)
                    sienna_total = sum(gen_dispatch.value)  # MWh (sum of MW over hours)
                    sienna_max = maximum(gen_dispatch.value)  # MW
                    sienna_avg = mean(gen_dispatch.value)  # MW
                    zero_count = count(==(0.0), gen_dispatch.value)
                    
                    # Utilization: actual total vs theoretical max (if dispatched at ts_max for all timesteps)
                    # Theoretical max is: if generator was dispatched at ts_max_mw for all timesteps
                    theoretical_max_mwh = ts_max_mw * length(gen_dispatch.value)
                    utilization = theoretical_max_mwh > 0 ? (sienna_total / theoretical_max_mwh * 100) : 0.0
                    
                    push!(hydro_summary, (
                        gen_name,
                        base_power,  # Use base_power (nameplate) instead of capacity
                        ts_max_mw,
                        sienna_total,
                        sienna_max,
                        sienna_avg,
                        zero_count,
                        utilization
                    ))
                    
                    println(lpad(gen_name, 25), " | ",
                            lpad(@sprintf("%.2f", base_power), 15), " | ",
                            lpad(@sprintf("%.2f", ts_max_mw), 15), " | ",
                            lpad(@sprintf("%.2f", sienna_total), 18), " | ",
                            lpad(@sprintf("%.2f", sienna_max), 15), " | ",
                            lpad(@sprintf("%.2f", sienna_avg), 15), " | ",
                            lpad(string(zero_count), 15))
                else
                    println(lpad(gen_name, 25), " | ",
                            lpad(@sprintf("%.2f", base_power), 15), " | ",
                            lpad(@sprintf("%.2f", ts_max_mw), 15), " | ",
                            "NO DISPATCH DATA", " | ",
                            "NO DISPATCH DATA", " | ",
                            "NO DISPATCH DATA", " | ",
                            "N/A")
                end
            end
            
            # Summary statistics
            println("\n" * "-"^80)
            println("SUMMARY STATISTICS:")
            println("-"^80)
            if !isempty(hydro_summary)
                local total_capacity = sum(hydro_summary.capacity_mw)
                local total_ts_max = sum(hydro_summary.ts_max_mw)
                local total_sienna = sum(hydro_summary.sienna_total_mwh)
                local total_zero = sum(hydro_summary.zero_timesteps)
                local avg_utilization = isempty(hydro_summary.utilization_pct) ? 0.0 : mean(hydro_summary.utilization_pct)
                
                println("Total Capacity: $(round(total_capacity, digits=2)) MW")
                println("Total TS Max (sum of maxes): $(round(total_ts_max, digits=2)) MW")
                println("Total Sienna Dispatch: $(round(total_sienna, digits=2)) MWh")
                local theoretical_max = total_ts_max * 168
                println("Theoretical Max (if all at TS max for all timesteps): $(round(theoretical_max, digits=2)) MWh")
                if theoretical_max > 0
                    local utilization_pct = (total_sienna / theoretical_max * 100)
                    println("Sienna Utilization: $(round(utilization_pct, digits=1))%")
                else
                    println("Sienna Utilization: N/A (no theoretical max)")
                end
                println("Total Zero Dispatch Timesteps: $total_zero")
                println("Average Generator Utilization: $(round(avg_utilization, digits=1))%")
            end
        catch e
            println("  Could not generate hydro comparison: $e")
            println("  Stacktrace:")
            for (exc, bt) in Base.catch_stack()
                showerror(stdout, exc, bt)
                println()
            end
        end
    end
else
    println("\n⚠️  No objective value to write (model failed)")
end

