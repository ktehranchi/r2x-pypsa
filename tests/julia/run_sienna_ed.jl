#!/usr/bin/env julia
# Run Sienna Economic Dispatch and return objective value
# 
# Usage:
#   julia run_sienna_ed.jl <json_file> <output_file>
# 
# Always loads system from JSON and creates template fresh (no caching).

# Activate local environment for reproducible package versions
# Note: Can also use `julia --project=tests/julia` flag to activate before script runs
import Pkg
Pkg.activate(joinpath(@__DIR__))

using PowerSystems
using PowerSystems: get_time_series_array, DeterministicSingleTimeSeries, PrimeMovers
using PowerSimulations
using PowerSimulations: ActivePowerTimeSeriesParameter, ActivePowerVariable, ActivePowerOutVariable, ActivePowerInVariable, RampConstraint, get_optimization_container, get_constraint, RateofChangeConstraintSlackDown, RateofChangeConstraintSlackUp, get_variable, FlowActivePowerVariable, FlowLimitConstraint, ConstraintKey, ExpressionKey, ActivePowerBalance, VariableKey, has_container_key, get_expression, get_branch_models, get_network_model, get_component_type, get_time_steps
using JuMP
using MathOptInterface
const MOI = MathOptInterface
using HiGHS
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
    json_file = "test_output/test_network_1h_output_optimized.json"
    output_file = "test_output/sienna_objective.txt"
    println("Using default paths (run with args for custom paths):")
    println("  JSON: $json_file")
    println("  Output: $output_file")
end

# Load system from JSON (always fresh, no caching)
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
# Explicitly disable ramp slack variables to enforce strict ramp constraints
thermal_model = DeviceModel(ThermalStandard, ThermalStandardDispatch; use_slacks = false)
set_device_model!(template, thermal_model)
set_device_model!(template, RenewableDispatch, RenewableFullDispatch)

# Configure StaticPowerLoad - use default "max_active_power" time series name
# Note: There was a PowerSystems v5 bug where get_max_active_power() returns MW instead of per-unit
# when a time series named "max_active_power" exists, but this may have been fixed or the workaround
# using "active_power" may be causing scaling issues. Reverting to default to test.
set_device_model!(template, PowerLoad, StaticPowerLoad)

# Check for storage units (will be dispatched if present in system)
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
                    "energy_target" => false,  # Enable energy target to enforce initial = final SOC (cyclic constraint)
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
# AreaBalancePowerModel enforces area-based balance with transmission constraints
# using AreaInterchange components. It represents each area as a single node and
# enforces flow limits between areas via AreaInterchange components.
# This is simpler than AreaPTDFPowerModel (no PTDF matrices needed).
set_network_model!(template, NetworkModel(AreaBalancePowerModel))
println("✓ Set network model: AreaBalancePowerModel (enforces area balance with AreaInterchange flow limits)")

# Configure AreaInterchange device model (required for AreaBalancePowerModel to work)
# StaticBranch formulation enforces flow limits from AreaInterchange components
if !isempty(collect(get_components(AreaInterchange, sys)))
    area_interchange_model = DeviceModel(AreaInterchange, StaticBranch)
    set_device_model!(template, area_interchange_model)
    println("✓ Set AreaInterchange model: StaticBranch (enforces flow limits)")
else
    println("⚠ No AreaInterchange components found - transmission constraints will not be enforced")
end

# Debug: Print system components
println("\nSystem components:")
println("  Buses: $(length(collect(get_components(ACBus, sys))))")
println("  PowerLoads: $(length(collect(get_components(PowerLoad, sys))))")
println("  ThermalStandard: $(length(collect(get_components(ThermalStandard, sys))))")
println("  RenewableDispatch: $(length(collect(get_components(RenewableDispatch, sys)))) (includes hydro)")
println("  EnergyReservoirStorage: $(length(collect(get_components(EnergyReservoirStorage, sys))))")

# Check if all buses have Areas (REQUIRED for AreaBalancePowerModel)
println("\nChecking Area assignments (REQUIRED for AreaBalancePowerModel):")
buses = collect(get_components(ACBus, sys))
areas = collect(get_components(Area, sys))
println("  Total Areas in system: $(length(areas))")
if !isempty(areas)
    println("  Area names: $(collect(get_name(a) for a in areas))")
end

buses_without_areas = [b for b in buses if PSY.get_area(b) === nothing]
if !isempty(buses_without_areas)
    println("  ✗ ERROR: $(length(buses_without_areas)) buses do NOT have Areas assigned:")
    for b in buses_without_areas[1:min(5, length(buses_without_areas))]
        println("    - $(get_name(b)) (bus number: $(get_number(b)))")
    end
    if length(buses_without_areas) > 5
        println("    ... and $(length(buses_without_areas) - 5) more")
    end
    println("  AreaBalancePowerModel REQUIRES all buses to have Areas assigned!")
    println("  This is likely the cause of the build failure.")
else
    println("  ✓ All buses have Areas assigned")
end

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

# Debug: Print ramp limits for nuclear generators
println("\nNuclear generator ramp limits:")
nuclear_gens = [g for g in thermal_gens if get_fuel(g) == ThermalFuels.NUCLEAR]
if !isempty(nuclear_gens)
    for gen in nuclear_gens
        ramp_limits = get_ramp_limits(gen)
        if ramp_limits !== nothing
            # Note: get_ramp_limits() returns values in the current unit system
            # PowerSimulations uses SYSTEM_BASE, so constraints use per-unit values
            # But we check here to see the values in the current unit system
            current_units = get_units_base(sys)
            rating_mw = get_rating(gen)  # Returns value in current unit system
            base_power = get_base_power(gen)
            max_power = get_max_active_power(gen)
            rating_pu = rating_mw / base_power  # Convert to per-unit
            println("  Generator: $(get_name(gen))")
            println("    Current unit system: $current_units")
            println("    Rating: $(rating_mw) MW ($(rating_pu) pu), Base power: $(base_power) MVA, Max power: $(max_power) MW")
            # get_ramp_limits() returns values in current unit system
            # In NATURAL_UNITS: MW/min, in SYSTEM_BASE: pu/min
            println("    Ramp limits (in $current_units): up=$(ramp_limits.up), down=$(ramp_limits.down)")
            if current_units == "NATURAL_UNITS"
                println("    Ramp limits (MW/min): up=$(ramp_limits.up) MW/min, down=$(ramp_limits.down) MW/min")
                ramp_limits_pu = (up = ramp_limits.up / base_power, down = ramp_limits.down / base_power)
                println("    Ramp limits (pu/min): up=$(ramp_limits_pu.up) pu/min, down=$(ramp_limits_pu.down) pu/min")
                println("    Max ramp down per hour (60 min): $(ramp_limits.down * 60) MW/h")
            else
                # Already in per-unit
                println("    Ramp limits (pu/min): up=$(ramp_limits.up) pu/min, down=$(ramp_limits.down) pu/min")
                ramp_limits_mw = (up = ramp_limits.up * base_power, down = ramp_limits.down * base_power)
                println("    Ramp limits (MW/min): up=$(ramp_limits_mw.up) MW/min, down=$(ramp_limits_mw.down) MW/min")
                println("    Max ramp down per hour (60 min): $(ramp_limits.down * 60) pu/h = $(ramp_limits.down * 60 * base_power) MW/h")
            end
            # Verify conversion from PyPSA: if PyPSA has 0.325 pu/h, expected ramp_down_pu_per_min = (0.325 * rating_pu) / 60.0
            expected_ramp_down_pu_per_min = (0.325 * rating_pu) / 60.0
            expected_ramp_down_mw_per_min = expected_ramp_down_pu_per_min * base_power
            println("    Expected from PyPSA (0.325 pu/h): $(expected_ramp_down_pu_per_min) pu/min = $(expected_ramp_down_mw_per_min) MW/min")
            println("    Actual vs Expected ratio: $(ramp_limits.down / expected_ramp_down_mw_per_min)")
        else
            println("  Generator: $(get_name(gen)) - No ramp limits set")
        end
    end
else
    println("  No nuclear generators found")
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

# ============================================================================
# VERIFY TRANSMISSION COMPONENTS (Line vs AreaInterchange)
# ============================================================================
println("\n" * "="^80)
println("VERIFYING TRANSMISSION COMPONENTS")
println("="^80)

# Store interchange_count in global scope for diagnostics
global interchange_count = 0
try
    # Check for Line components (actual transmission branches connecting buses)
    local lines = collect(get_components(Line, sys))
    local line_count = length(lines)
    
    # Check for AreaInterchange components (area-to-area flow limits)
    local area_interchanges = collect(get_components(AreaInterchange, sys))
    global interchange_count = length(area_interchanges)
    
    # Check for other branch types
    local transformers = collect(get_components(Transformer2W, sys))
    local transformer_count = length(transformers)
    
    println("\nTransmission Component Counts:")
    println("  Line components (bus-to-bus): $line_count")
    println("  AreaInterchange components (area-to-area): $interchange_count")
    println("  Transformer2W components: $transformer_count")
    
    if line_count == 0 && interchange_count > 0
        println("\n✓ Area-based transmission model detected:")
        println("  - System has $interchange_count AreaInterchange components")
        println("  - AreaBalancePowerModel uses AreaInterchange to enforce area-to-area flow limits")
        println("  - No Line components needed - each area is treated as a single aggregated node")
        println("  - Power balance is enforced per area, with transmission constraints via AreaInterchange")
    elseif line_count > 0
        println("\n✓ Line components found: $line_count")
        println("  - These enable bus-to-bus power flow")
    end
    
    # Check what device models are configured for branches
    println("\nBranch Device Models in Template:")
    try
        if haskey(template.branches, :Line)
            println("  ✓ Line: $(template.branches[:Line])")
        else
            println("  ✗ Line: NOT CONFIGURED")
        end
        
        if haskey(template.branches, :AreaInterchange)
            println("  ✓ AreaInterchange: $(template.branches[:AreaInterchange])")
        else
            println("  ✗ AreaInterchange: NOT CONFIGURED")
        end
        
        if haskey(template.branches, :Transformer2W)
            println("  ✓ Transformer2W: $(template.branches[:Transformer2W])")
        else
            println("  ✗ Transformer2W: NOT CONFIGURED")
        end
    catch e
        println("  Could not check device models: $e")
    end
    
    # Check network model type
    println("\nNetwork Model:")
    try
        network_model = template.network_model
        network_formulation = get_network_formulation(network_model)
        println("  Network model: $network_formulation")
    catch e
        println("  Could not determine network model: $e")
    end
    
    # Check subnetworks (this is the KEY issue!)
    println("\nSubnetworks (CRITICAL FOR COPPERPLATE):")
    try
        # For AreaBalancePowerModel, subnetworks are determined from Area topology
        # Areas are connected via AreaInterchange components
        # This is handled automatically when the model is built
        println("  NOTE: For AreaBalancePowerModel, subnetworks are determined from Area topology")
        println("  - Areas are connected via AreaInterchange components")
        println("  - Subnetworks are automatically determined when the model is built")
        println("  - Balance is enforced PER AREA with transmission constraints via AreaInterchange flow limits")
        println("\n  This will be verified after model is built (see below)")
    catch e
        println("  Could not explain subnetworks: $e")
    end
    
    # Show sample AreaInterchange details if they exist
    if interchange_count > 0
        println("\nSample AreaInterchange components (first 5):")
        for (i, ai) in enumerate(area_interchanges[1:min(5, interchange_count)])
            println("  $i. $(get_name(ai)): $(get_name(ai.from_area)) -> $(get_name(ai.to_area))")
            println("     Flow limits: $(ai.flow_limits)")
        end
        if interchange_count > 5
            println("  ... and $(interchange_count - 5) more")
        end
    end
    
    # Show sample Line details if they exist
    if line_count > 0
        println("\nSample Line components (first 5):")
        for (i, line) in enumerate(lines[1:min(5, line_count)])
            from_bus = get_from_bus(line)
            to_bus = get_to_bus(line)
            println("  $i. $(get_name(line)): $(get_name(from_bus)) -> $(get_name(to_bus))")
            println("     Rating: $(get_rating(line)) MVA")
        end
        if line_count > 5
            println("  ... and $(line_count - 5) more")
        end
    end
    
catch e
    println("ERROR: Could not verify transmission components: $e")
    println("  Stacktrace:")
    for (exc, bt) in Base.catch_stack()
        showerror(stdout, exc, bt)
        println()
    end
end

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
    time_steps_to_check = [1, 5, 10, 24, 61, 62, 63]  # Add timestep 62 and neighbors
    
    for step in time_steps_to_check
        local total_load = 0.0
        local total_thermal_available = 0.0
        local total_renewable_available = 0.0
        local total_hydro_available = 0.0
        local total_thermal_min = 0.0  # Track minimum generation requirements
        
        # Sum loads at this time step
        # Time series values are already scaled to MW via scaling_factor_multiplier = get_max_active_power
        for load in loads
            try
                ts_data = get_time_series_array(DeterministicSingleTimeSeries, load, "max_active_power")
                if ts_data !== nothing && length(ts_data) > step
                    ts_value = TimeSeries.values(ts_data)[step]
                    # Time series already in MW (scaled by scaling_factor_multiplier)
                    total_load += abs(ts_value)
                else
                    # No time series, use static max
                    total_load += get_max_active_power(load)
                end
            catch
                # Use static value if no time series
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
        
        # Add storage debugging
        local total_storage_discharge_available = 0.0
        local total_storage_charge_available = 0.0
        local total_storage_energy_available = 0.0
        
        for s in storage_units
            try
                # Check discharge capacity
                output_limits = get_output_active_power_limits(s)
                total_storage_discharge_available += output_limits.max
                
                # Check charge capacity
                input_limits = get_input_active_power_limits(s)
                total_storage_charge_available += input_limits.max
                
                # Check energy available (for discharging)
                storage_cap = get_storage_capacity(s)
                initial_soc = get_initial_storage_capacity_level(s)
                # Estimate energy available at this timestep (simplified - doesn't account for previous charging/discharging)
                total_storage_energy_available += initial_soc * storage_cap
            catch
            end
        end
        
        println("      - Storage discharge: $(round(total_storage_discharge_available, digits=2)) MW")
        println("      - Storage charge: $(round(total_storage_charge_available, digits=2)) MW")
        println("      - Storage energy available: $(round(total_storage_energy_available, digits=2)) MWh")
    end
catch e
    println("  Could not check load vs generation: $e")
end

# ============================================================================
# BUS 5 AVAILABILITY AT TIMESTEP 62 (per carrier)
# ============================================================================
println("\n" * "="^80)
println("BUS 5 AVAILABILITY AT TIMESTEP 62 (per carrier)")
println("="^80)
try
    # Get bus 5
    local bus5 = get_bus(sys, 5)
    if bus5 === nothing
        println("  Bus 5 not found in system")
    else
        println("  Bus 5 found: $(get_name(bus5))")
        
        # Get all generators and filter by bus 5
        local all_thermal = collect(get_components(ThermalStandard, sys))
        local all_renewable = collect(get_components(RenewableDispatch, sys))
        local all_storage = collect(get_components(EnergyReservoirStorage, sys))
        
        # Filter generators by bus number 5
        local thermal_bus5 = [g for g in all_thermal if get_number(get_bus(g)) == 5]
        local renewable_bus5 = [g for g in all_renewable if get_number(get_bus(g)) == 5]
        local storage_bus5 = [g for g in all_storage if get_number(get_bus(g)) == 5]
        
        println("\n  Generators at bus 5:")
        println("    Thermal: $(length(thermal_bus5))")
        println("    Renewable: $(length(renewable_bus5))")
        println("    Storage: $(length(storage_bus5))")
        
        # Get loads at bus 5 and calculate load at timestep 62
        local all_loads = collect(get_components(PowerLoad, sys))
        local loads_bus5 = [l for l in all_loads if get_number(get_bus(l)) == 5]
        local timestep = 62  # 0-indexed, so timestep 62 = index 62
        local total_load_bus5 = 0.0
        
        println("\n  Loads at bus 5: $(length(loads_bus5))")
        
        for load in loads_bus5
            try
                local ts_data = get_time_series_array(DeterministicSingleTimeSeries, load, "max_active_power")
                if ts_data !== nothing && length(ts_data) > timestep
                    local ts_value = TimeSeries.values(ts_data)[timestep]
                    # Time series already in MW (scaled by scaling_factor_multiplier)
                    total_load_bus5 += abs(ts_value)
                else
                    # No time series, use static max
                    total_load_bus5 += get_max_active_power(load)
                end
            catch
                # Use static value if no time series
                total_load_bus5 += get_max_active_power(load)
            end
        end
        
        println("  Total Load at Timestep 62: $(@sprintf("%.2f", total_load_bus5)) MW")
        
        # Group by carrier and calculate availability at timestep 62
        # Dictionary to store carrier groups: carrier_name => (generators, total_availability, details)
        local carrier_groups = Dict{String, Tuple{Vector, Float64, Vector{Tuple{String, Float64, Float64}}}}()
        
        # Process thermal generators (aggregate all together)
        if !isempty(thermal_bus5)
            local carrier = "Thermal"
            local total_thermal_availability = 0.0
            local thermal_details = Vector{Tuple{String, Float64, Float64}}()
            
            for gen in thermal_bus5
                try
                    local capacity = get_max_active_power(gen)  # MW
                    local availability = capacity  # Thermal is always available at full capacity
                    total_thermal_availability += availability
                    push!(thermal_details, (get_name(gen), capacity, availability))
                catch e
                    println("    WARNING: Could not process thermal generator $(get_name(gen)): $e")
                end
            end
            
            if !isempty(thermal_details)
                carrier_groups[carrier] = (thermal_bus5, total_thermal_availability, thermal_details)
            end
        end
        
        # Process renewable generators (group by prime mover type)
        for gen in renewable_bus5
            try
                local pm = get_prime_mover_type(gen)
                local carrier = ""
                if pm == PrimeMovers.PVe
                    carrier = "Solar (PVe)"
                elseif pm in [PrimeMovers.WT, PrimeMovers.WS]
                    carrier = "Wind ($pm)"
                elseif pm == PrimeMovers.HY
                    carrier = "Hydro (HY)"
                else
                    carrier = "Renewable ($pm)"
                end
                
                local capacity = get_max_active_power(gen)  # MW
                local availability = capacity  # Default to full capacity
                
                # Check time series for availability at timestep 62
                try
                    local ts_data = get_time_series_array(DeterministicSingleTimeSeries, gen, "max_active_power"; ignore_scaling_factors=true)
                    if ts_data !== nothing && length(ts_data) > timestep
                        local ts_values = TimeSeries.values(ts_data)
                        local ts_value_pu = ts_values[timestep]  # Per-unit (0-1)
                        availability = ts_value_pu * capacity  # Convert to MW
                    end
                catch
                    # No time series, use full capacity
                end
                
                if !haskey(carrier_groups, carrier)
                    carrier_groups[carrier] = (Vector{Any}(), 0.0, Vector{Tuple{String, Float64, Float64}}())
                end
                
                local (gens, total, details) = carrier_groups[carrier]
                push!(gens, gen)
                push!(details, (get_name(gen), capacity, availability))
                carrier_groups[carrier] = (gens, total + availability, details)
            catch e
                println("    WARNING: Could not process renewable generator $(get_name(gen)): $e")
            end
        end
        
        # Process storage units
        if !isempty(storage_bus5)
            local carrier = "Storage"
            local total_storage_availability = 0.0
            local storage_details = Vector{Tuple{String, Float64, Float64}}()
            
            for s in storage_bus5
                try
                    local output_limits = get_output_active_power_limits(s)
                    local capacity = output_limits.max  # Discharge capacity in MW
                    local availability = capacity  # Default to full capacity
                    
                    # Check time series for discharge capacity at timestep 62
                    try
                        local ts_data = get_time_series_array(DeterministicSingleTimeSeries, s, "max_active_power"; ignore_scaling_factors=true)
                        if ts_data !== nothing && length(ts_data) > timestep
                            local ts_values = TimeSeries.values(ts_data)
                            local ts_value_pu = ts_values[timestep]  # Per-unit (0-1)
                            availability = ts_value_pu * capacity  # Convert to MW
                        end
                    catch
                        # No time series, use full capacity
                    end
                    
                    total_storage_availability += availability
                    push!(storage_details, (get_name(s), capacity, availability))
                catch e
                    println("    WARNING: Could not process storage unit $(get_name(s)): $e")
                end
            end
            
            if !isempty(storage_details)
                carrier_groups[carrier] = (storage_bus5, total_storage_availability, storage_details)
            end
        end
        
        # Display results
        println("\n" * "-"^80)
        println("SUMMARY AT TIMESTEP 62:")
        println("  Total Load: $(@sprintf("%.2f", total_load_bus5)) MW")
        
        # Calculate total available generation
        local total_available_gen = 0.0
        for (carrier, (gens, total_avail, details)) in carrier_groups
            total_available_gen += total_avail
        end
        println("  Total Available Generation: $(@sprintf("%.2f", total_available_gen)) MW")
        println("  Balance (Available - Load): $(@sprintf("%.2f", total_available_gen - total_load_bus5)) MW")
        
        if total_load_bus5 > total_available_gen
            println("  ⚠️  WARNING: Load exceeds available generation!")
        end
        
        if isempty(carrier_groups)
            println("\n  No generators found at bus 5")
        else
            println("\n" * "-"^80)
            println("AVAILABILITY BY CARRIER:")
            for (carrier, (gens, total_avail, details)) in sort(collect(carrier_groups), by=x -> x[1])
                println("\n  Carrier: $carrier")
                println("    Generators: $(length(gens))")
                println("    Total Availability: $(@sprintf("%.2f", total_avail)) MW")
                
                if !isempty(details)
                    # Sort by availability (descending) and show top 10
                    sort!(details, by=x -> x[3], rev=true)
                    println("    Top generators:")
                    for (i, (name, capacity, avail)) in enumerate(details[1:min(10, length(details))])
                        println("      $name: $(@sprintf("%.2f", avail)) MW (capacity: $(@sprintf("%.2f", capacity)) MW)")
                    end
                    if length(details) > 10
                        println("      ... and $(length(details) - 10) more")
                    end
                end
            end
        end
    end
catch e
    println("ERROR: Could not check bus 5 availability: $e")
    println("  Stacktrace:")
    for (exc, bt) in Base.catch_stack()
        showerror(stdout, exc, bt)
        println()
    end
end

# Validate storage resources at first timestep
println("\n" * "="^80)
println("VALIDATING STORAGE RESOURCES AT FIRST TIMESTEP")
println("="^80)
try
    # Get all storage units
    local storage_units = collect(get_components(EnergyReservoirStorage, sys))
    
    println("\nStorage units found: $(length(storage_units))")
    
    if !isempty(storage_units)
        # Calculate total storage capacity
        total_storage_discharge_capacity = 0.0
        total_storage_charge_capacity = 0.0
        total_storage_energy_capacity = 0.0
        storage_details = []
        
        for s in storage_units
            storage_name = get_name(s)
            
            # Get static limits (already in MW with NATURAL_UNITS)
            output_limits = get_output_active_power_limits(s)  # Discharge (MW)
            input_limits = get_input_active_power_limits(s)   # Charge (MW)
            storage_cap = get_storage_capacity(s)  # Energy capacity (MWh)
            initial_soc = get_initial_storage_capacity_level(s)  # Fraction 0-1
            base_power = get_base_power(s)
            rating = get_rating(s)  # Per-unit rating
            
            # Get time series for max_active_power (discharge) and min_active_power (charge) if they exist
            discharge_upper_bound_mw = output_limits.max  # Default to static limit
            charge_upper_bound_mw = input_limits.max     # Default to static limit
            
            # Check for discharge time series (max_active_power)
            try
                ts_data = get_time_series_array(DeterministicSingleTimeSeries, s, "max_active_power"; ignore_scaling_factors=true)
                if ts_data !== nothing && length(ts_data) > 0
                    ts_values = TimeSeries.values(ts_data)
                    ts_value_ts1_pu = ts_values[1]  # First timestep (per-unit 0-1)
                    # Upper bound = ts_value_pu * get_output_active_power_limits().max
                    # But we need to check if PowerSimulations uses get_rating() or get_output_active_power_limits().max
                    # For now, use output_limits.max as the multiplier (matches static limit)
                    discharge_upper_bound_mw = ts_value_ts1_pu * output_limits.max
                end
            catch
                # No time series for discharge
            end
            
            # Check for charge time series (min_active_power - note: negative for charging)
            try
                ts_data = get_time_series_array(DeterministicSingleTimeSeries, s, "min_active_power"; ignore_scaling_factors=true)
                if ts_data !== nothing && length(ts_data) > 0
                    ts_values = TimeSeries.values(ts_data)
                    ts_value_ts1_pu = ts_values[1]  # First timestep (per-unit, typically negative for charging)
                    # For charging, the limit is typically the absolute value
                    charge_upper_bound_mw = abs(ts_value_ts1_pu) * input_limits.max
                end
            catch
                # No time series for charge
            end
            
            total_storage_discharge_capacity += discharge_upper_bound_mw
            total_storage_charge_capacity += charge_upper_bound_mw
            total_storage_energy_capacity += storage_cap
            
            push!(storage_details, (
                name = storage_name,
                discharge_capacity_mw = output_limits.max,
                charge_capacity_mw = input_limits.max,
                energy_capacity_mwh = storage_cap,
                initial_soc = initial_soc,
                discharge_upper_bound_mw = discharge_upper_bound_mw,
                charge_upper_bound_mw = charge_upper_bound_mw,
                initial_energy_mwh = initial_soc * storage_cap
            ))
        end
        
        println("\nStorage capacity constraints at first timestep:")
        println("  Total discharge capacity (upper bound): $(@sprintf("%.2f", total_storage_discharge_capacity)) MW")
        println("  Total charge capacity (upper bound): $(@sprintf("%.2f", total_storage_charge_capacity)) MW")
        println("  Total energy capacity: $(@sprintf("%.2f", total_storage_energy_capacity)) MWh")
        println("\n  NOTE: This shows capacity constraints (upper bounds), not actual dispatch.")
        println("  Actual dispatch values will be compared after optimization.")
        
        # Show top 10 storage units
        if length(storage_details) > 0
            sort!(storage_details, by=x -> x.discharge_capacity_mw, rev=true)
            println("\nTop 10 storage units at first timestep:")
            println("  " * lpad("Name", 40) * lpad("Discharge (MW)", 15) * lpad("Charge (MW)", 15) * lpad("Energy (MWh)", 15) * lpad("Initial SOC", 12))
            println("  " * "-"^97)
            for (i, detail) in enumerate(storage_details[1:min(10, length(storage_details))])
                println("  " * lpad(detail.name, 40) * lpad(@sprintf("%.2f", detail.discharge_capacity_mw), 15) * 
                        lpad(@sprintf("%.2f", detail.charge_capacity_mw), 15) * lpad(@sprintf("%.2f", detail.energy_capacity_mwh), 15) *
                        lpad(@sprintf("%.4f", detail.initial_soc), 12))
            end
        end
        
        # Read PyPSA storage dispatch from the test output if available
        pypsa_dispatch_file = joinpath(@__DIR__, "test_output", "pypsa_dispatch.csv")
        if isfile(pypsa_dispatch_file)
            try
                pypsa_df = CSV.read(pypsa_dispatch_file, DataFrame)
                # Filter for storage carriers at first timestep
                # PyPSA storage might be in "StorageUnit" or have specific carrier names
                first_ts = first(unique(pypsa_df.DateTime))
                # Check what storage-related columns exist
                storage_rows = filter(row -> occursin("storage", lowercase(row.carrier)) || 
                                            occursin("battery", lowercase(row.carrier)) ||
                                            row.carrier == "battery", pypsa_df)
                storage_rows_ts1 = filter(row -> row.DateTime == first_ts, storage_rows)
                
                if !isempty(storage_rows_ts1)
                    # Separate charge (negative) and discharge (positive)
                    pypsa_storage_discharge = sum(filter(row -> row.value > 0, storage_rows_ts1).value)
                    pypsa_storage_charge = abs(sum(filter(row -> row.value < 0, storage_rows_ts1).value))
                    
                    println("\n" * "-"^80)
                    println("COMPARISON WITH PyPSA (CAPACITY CONSTRAINTS):")
                    println("  Sienna storage discharge capacity (TS1): $(@sprintf("%.2f", total_storage_discharge_capacity)) MW")
                    println("  PyPSA storage discharge (TS1): $(@sprintf("%.2f", pypsa_storage_discharge)) MW")
                    println("  Sienna storage charge capacity (TS1): $(@sprintf("%.2f", total_storage_charge_capacity)) MW")
                    println("  PyPSA storage charge (TS1): $(@sprintf("%.2f", pypsa_storage_charge)) MW")
                    println("\n  NOTE: Comparing capacity constraints vs actual dispatch.")
                    println("  Actual dispatch comparison will be done after optimization.")
                else
                    println("\n  (No storage dispatch found in PyPSA file for comparison)")
                end
            catch e
                println("\n  Could not read PyPSA dispatch file for comparison: $e")
            end
        else
            println("\n  (PyPSA dispatch file not found for comparison)")
        end
    else
        println("  No storage units found in system")
    end
    
catch e
    println("ERROR: Could not validate storage resources: $e")
    println("  Stacktrace:")
    for (exc, bt) in Base.catch_stack()
        showerror(stdout, exc, bt)
        println()
    end
end

println("="^80)

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
        HiGHS.Optimizer,
        "output_flag" => true,  # Enable output to see details
        "primal_feasibility_tolerance" => 1e-9,  # Tight tolerance for better precision
        "dual_feasibility_tolerance" => 1e-9,  # Tight tolerance for better precision
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
println("\nBuilding model...")
output_dir = mktempdir()
build!(model; output_dir=output_dir)
println("  ✓ Model built successfully")

# ============================================================================
# VERIFY AREABALANCEPOWERMODEL IS WORKING
# ============================================================================
println("\n" * "="^80)
println("VERIFYING AREABALANCEPOWERMODEL CONFIGURATION")
println("="^80)

try
    container = get_optimization_container(model)
    time_steps = get_time_steps(container)
    num_time_steps = length(time_steps)
    
    # Quick verification summary
    println("\nAreaBalancePowerModel Status:")
    
    # 1. Check variables
    has_vars = has_container_key(container, FlowActivePowerVariable, AreaInterchange)
    if has_vars
        flow_vars = get_variable(container, FlowActivePowerVariable(), AreaInterchange)
        var_count = length(flow_vars)
        expected_vars = interchange_count * num_time_steps
        println("  ✓ FlowActivePowerVariable: $var_count variables ($interchange_count interchanges × $num_time_steps time steps)")
        if var_count != expected_vars
            println("    ⚠️  Expected $expected_vars variables")
        end
    else
        println("  ✗ FlowActivePowerVariable: NOT FOUND")
    end
    
    # 2. Check constraints
    has_ub = has_container_key(container, FlowLimitConstraint, AreaInterchange, "ub")
    has_lb = has_container_key(container, FlowLimitConstraint, AreaInterchange, "lb")
    if has_ub && has_lb
        ub_constraints = get_constraint(container, FlowLimitConstraint(), AreaInterchange, "ub")
        lb_constraints = get_constraint(container, FlowLimitConstraint(), AreaInterchange, "lb")
        ub_count = length(ub_constraints)
        lb_count = length(lb_constraints)
        expected_constraints = interchange_count * num_time_steps
        println("  ✓ FlowLimitConstraint: $ub_count upper + $lb_count lower bounds")
        if ub_count != expected_constraints || lb_count != expected_constraints
            println("    ⚠️  Expected $expected_constraints each")
        end
    else
        println("  ✗ FlowLimitConstraint: NOT FOUND")
    end
    
    # 3. Check power balance
    has_balance = has_container_key(container, ActivePowerBalance, Area)
    if has_balance
        area_expr = get_expression(container, ActivePowerBalance(), Area)
        println("  ✓ ActivePowerBalance: Area-based balance expressions created")
    else
        println("  ✗ ActivePowerBalance: NOT FOUND")
    end
    
    # Summary
    println("\nSummary:")
    if has_vars && has_ub && has_lb && has_balance
        println("  ✓ AreaBalancePowerModel is correctly configured!")
        println("  ✓ Transmission constraints are being enforced via AreaInterchange flow limits")
        println("  ✓ Power balance is enforced per area with inter-area flow constraints")
    else
        println("  ✗ AreaBalancePowerModel configuration incomplete")
        println("    Check the errors above")
    end
    
catch e
    println("  ✗ Error verifying AreaBalancePowerModel: $e")
end

println("="^80)

# DEBUG: Check ramp constraints for nuclear generators
println("\n" * "="^80)
println("DEBUGGING RAMP CONSTRAINTS FOR NUCLEAR GENERATORS")
println("="^80)
try
    container = get_optimization_container(model)
    # Get resolution from system's time series (or default to 1 hour)
    resolutions = get_time_series_resolutions(sys)
    if !isempty(resolutions)
        resolution = first(resolutions)  # Use first resolution found
        minutes_per_period = Dates.value(Dates.Minute(resolution))
    else
        # Default to 1 hour if no time series found
        minutes_per_period = 60
        resolution = Dates.Hour(1)
    end
    println("  Time resolution: $resolution")
    println("  Minutes per period: $minutes_per_period")
    
    # Get nuclear generators
    local nuclear_gens = [g for g in collect(get_components(ThermalStandard, sys)) if get_fuel(g) == ThermalFuels.NUCLEAR]
    
    for gen in nuclear_gens
        name = get_name(gen)
        # Note: PowerSimulations uses SYSTEM_BASE, so get_ramp_limits() returns per-unit values
        # We need to check the unit system to interpret correctly
        current_units = get_units_base(sys)
        ramp_limits = get_ramp_limits(gen)
        initial_power = get_active_power(gen)
        base_power = get_base_power(gen)
        
        println("\n  Generator: $name")
        println("    Current unit system: $current_units")
        println("    Initial power: $initial_power (value depends on unit system)")
        if current_units == "SYSTEM_BASE"
            # Ramp limits are in per-unit per minute
            ramp_down_pu_per_min = ramp_limits.down
            ramp_down_mw_per_min = ramp_down_pu_per_min * base_power
            ramp_down_pu_per_h = ramp_down_pu_per_min * 60
            ramp_down_mw_per_h = ramp_down_mw_per_min * 60
            println("    Ramp limits (pu/min): down=$(ramp_down_pu_per_min) pu/min")
            println("    Ramp limits (MW/min): down=$(ramp_down_mw_per_min) MW/min")
            println("    Max ramp down per period: $(ramp_down_pu_per_min * minutes_per_period) pu = $(ramp_down_mw_per_min * minutes_per_period) MW")
        else
            # Ramp limits are in MW/min (NATURAL_UNITS)
            println("    Ramp limits (MW/min): down=$(ramp_limits.down) MW/min")
            println("    Max ramp down per period: $(ramp_limits.down * minutes_per_period) MW")
        end
        
        # Try to access ramp constraints
        try
            # Get all constraint keys from container
            constraint_keys = collect(keys(container.constraints))
            ramp_keys = [k for k in constraint_keys if occursin("RampConstraint", string(k))]
            
            if length(ramp_keys) > 0
                # Find the ramp down constraint key
                ramp_dn_key = nothing
                for key in ramp_keys
                    if occursin("\"dn\"", string(key)) || occursin("dn", string(key))
                        ramp_dn_key = key
                        break
                    end
                end
                
                if ramp_dn_key !== nothing
                    # Get the constraint container for ramp down
                    ramp_constraints_dn = container.constraints[ramp_dn_key]
                    
                    # DenseAxisArray uses array indexing, not haskey with tuples
                    try
                        # Try to access constraint for this generator at timestep 1
                        con = ramp_constraints_dn[name, 1]
                        con_obj = JuMP.constraint_object(con)
                        println("    ✓ Ramp DOWN constraint found for timestep 1")
                        println("    Constraint type: $(typeof(con_obj.func))")
                        println("    Constraint set: $(typeof(con_obj.set))")
                        
                        # Check if constraint uses expressions or variables
                        constraint_str = string(con_obj)
                        if occursin("ActivePowerRangeExpression", constraint_str)
                            println("    ⚠️  WARNING: Constraint uses EXPRESSIONS (ActivePowerRangeExpressionLB/UB)")
                            println("    This may not properly enforce ramp-down limits!")
                        elseif occursin("ActivePowerVariable", constraint_str)
                            println("    ✓ Constraint uses VARIABLES (ActivePowerVariable) - correct!")
                            # Show the actual constraint for timestep 2 (ramp between 1 and 2)
                            if name in first(axes(ramp_constraints_dn))
                                try
                                    con2 = ramp_constraints_dn[name, 2]
                                    con2_obj = JuMP.constraint_object(con2)
                                    constraint_str2 = string(con2_obj)
                                    println("    Constraint for timestep 2: $constraint_str2")
                                    
                                    # Extract the constraint RHS value
                                    # PowerSimulations uses SYSTEM_BASE, so constraint values are in per-unit
                                    # The constraint is: variable[t-1] - variable[t] >= -ramp_limit_pu_per_hour
                                    # For GreaterThan set, the lower bound is the RHS value
                                    if typeof(con2_obj.set) <: MOI.GreaterThan
                                        rhs_value = con2_obj.set.lower  # Get the lower bound (negative ramp limit)
                                        rhs_pu_per_h = abs(rhs_value)  # Per-unit per hour
                                        # Convert to MW/h for comparison (multiply by base_power)
                                        base_power_gen = get_base_power(gen)
                                        rhs_mw_per_h = rhs_pu_per_h * base_power_gen
                                        println("    Constraint RHS: $(rhs_pu_per_h) pu/h = $(rhs_mw_per_h) MW/h")
                                        
                                        # Get expected value - need to account for unit system
                                        # PowerSimulations uses SYSTEM_BASE, so ramp_limits.down is in pu/min
                                        expected_pu_per_h = ramp_limits.down * 60  # pu/min * 60 = pu/h
                                        expected_mw_per_h = expected_pu_per_h * base_power_gen
                                        println("    Expected from ramp_limits: $(expected_pu_per_h) pu/h = $(expected_mw_per_h) MW/h")
                                        diff = abs(rhs_mw_per_h - expected_mw_per_h)
                                        if diff < 0.1
                                            println("    ✓ Constraint value matches expected ramp limit!")
                                        else
                                            println("    ⚠️  Constraint value ($(rhs_mw_per_h) MW/h) differs from expected ($(expected_mw_per_h) MW/h) by $(diff) MW/h")
                                        end
                                    else
                                        println("    Constraint set type: $(typeof(con2_obj.set))")
                                    end
                                catch e
                                    println("    Could not access constraint for timestep 2: $e")
                                end
                            end
                        else
                            # Print first part of constraint to see structure
                            constraint_preview = length(constraint_str) > 300 ? constraint_str[1:300] * "..." : constraint_str
                            println("    ? Constraint structure (preview): $constraint_preview")
                        end
                    catch e
                        println("    ⚠️  WARNING: Could not access ramp DOWN constraint for timestep 1: $e")
                        # Show available generators in the constraint
                        try
                            available_gens = collect(first(axes(ramp_constraints_dn)))
                            println("    Available generators in ramp constraints: $(available_gens[1:min(5, length(available_gens))])")
                        catch
                        end
                    end
                else
                    println("    ⚠️  WARNING: Could not find ramp down constraint key")
                end
            else
                println("    ⚠️  WARNING: No ramp constraints found in the model!")
            end
        catch e
            println("    Could not access ramp constraints: $e")
            println("    Error type: $(typeof(e))")
        end
    end
catch e
    println("ERROR checking ramp constraints: $e")
    println("  Stacktrace:")
    for (exc, bt) in Base.catch_stack()
        showerror(stdout, exc, bt)
        println()
    end
end
println("="^80)
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
    
    # Check subnetworks in the built model (CRITICAL!)
    println("\n  Subnetworks in built model:")
    try
        # Get network model from template (access template field directly)
        # model.template is a ProblemTemplate, which has a network_model field
        network_model = model.template.network_model
        subnetworks = network_model.subnetworks
        println("    Number of subnetworks: $(length(subnetworks))")
        println("    Subnetwork keys: $(keys(subnetworks))")
        
        if length(subnetworks) > 1
            println("\n    ⚠️  WARNING: Multiple subnetworks detected!")
            println("    - Each subnetwork enforces its own balance constraint")
            println("    - This means buses are isolated - power cannot flow between subnetworks")
            println("    - With AreaBalancePowerModel, balance is enforced per area with AreaInterchange flow limits")
            println("    - This explains why wind is curtailed - it can only serve local load!")
            
            # Show sample subnetworks
            println("\n    Sample subnetworks (first 5):")
            for (i, (subnet_id, bus_set)) in enumerate(collect(subnetworks)[1:min(5, length(subnetworks))])
                println("      Subnetwork $subnet_id: $(length(bus_set)) buses - $(collect(bus_set)[1:min(5, length(bus_set))])...")
            end
        elseif length(subnetworks) == 1
            subnet_id = first(keys(subnetworks))
            bus_set = subnetworks[subnet_id]
            println("    ✓ Single subnetwork: $subnet_id with $(length(bus_set)) buses")
            println("    - This enables system-wide balance (copper plate)")
        else
            println("    ⚠️  No subnetworks found (unexpected)")
        end
        
        # Check bus_area_map
        if !isempty(network_model.bus_area_map)
            println("\n    Bus-to-subnetwork mapping:")
            bus_map_sample = collect(network_model.bus_area_map)[1:min(5, length(network_model.bus_area_map))]
            for (bus, subnet_id) in bus_map_sample
                println("      Bus $(get_name(bus)) (number $(get_number(bus))) -> Subnetwork $subnet_id")
            end
            if length(network_model.bus_area_map) > 5
                println("      ... and $(length(network_model.bus_area_map) - 5) more buses")
            end
        end
    catch e
        println("    Could not check subnetworks: $e")
        println("    (This is expected if model structure is not accessible)")
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
    
    # Check for ramp slack variables
    println("\n" * "="^80)
    println("CHECKING FOR RAMP SLACK VARIABLES")
    println("="^80)
    
    try
        container = get_optimization_container(model)
        
        # Get nuclear generators
        local nuclear_gens = [g for g in collect(get_components(ThermalStandard, sys)) if get_fuel(g) == ThermalFuels.NUCLEAR]
        
        # Check if RateofChangeConstraintSlackDown variables exist
        try
            slack_dn = get_variable(container, RateofChangeConstraintSlackDown(), ThermalStandard)
            println("  ⚠️  WARNING: RateofChangeConstraintSlackDown variables EXIST in container!")
            println("  This means slack variables were created even though use_slacks = false")
            
            # Check values for nuclear generators
            for gen in nuclear_gens
                name = get_name(gen)
                if name in first(axes(slack_dn))
                    for t in [1, 2, 3]
                        try
                            slack_val = JuMP.value(slack_dn[name, t])
                            if slack_val > 1e-6  # Non-zero slack
                                println("    Generator $name, timestep $t: slack_dn = $slack_val (NON-ZERO!)")
                            end
                        catch
                        end
                    end
                end
            end
        catch e
            println("  ✓ RateofChangeConstraintSlackDown variables do NOT exist (expected when use_slacks = false)")
        end
        
        # Check if RateofChangeConstraintSlackUp variables exist
        try
            slack_up = get_variable(container, RateofChangeConstraintSlackUp(), ThermalStandard)
            println("  ⚠️  WARNING: RateofChangeConstraintSlackUp variables EXIST in container!")
            
            for gen in nuclear_gens
                name = get_name(gen)
                if name in first(axes(slack_up))
                    for t in [1, 2, 3]
                        try
                            slack_val = JuMP.value(slack_up[name, t])
                            if slack_val > 1e-6
                                println("    Generator $name, timestep $t: slack_up = $slack_val (NON-ZERO!)")
                            end
                        catch
                        end
                    end
                end
            end
        catch e
            println("  ✓ RateofChangeConstraintSlackUp variables do NOT exist (expected when use_slacks = false)")
        end
        
        # Also check the actual constraint to see if slack terms are present
        println("\n  Checking constraint structure for slack terms...")
        
        # Find the ramp constraint key by searching through constraint keys
        constraint_keys = collect(keys(container.constraints))
        ramp_keys = [k for k in constraint_keys if occursin("RampConstraint", string(k))]
        
        if length(ramp_keys) > 0
            # Find the ramp down constraint key
            ramp_dn_key = nothing
            for key in ramp_keys
                if occursin("\"dn\"", string(key)) || occursin("dn", string(key))
                    ramp_dn_key = key
                    break
                end
            end
            
            if ramp_dn_key !== nothing
                ramp_constraints_dn = container.constraints[ramp_dn_key]
                for gen in nuclear_gens
                    name = get_name(gen)
                    try
                        if name in first(axes(ramp_constraints_dn))
                            con2 = ramp_constraints_dn[name, 2]
                            con2_obj = JuMP.constraint_object(con2)
                            constraint_str = string(con2_obj)
                            if occursin("RateofChangeConstraintSlack", constraint_str) || occursin("slack", lowercase(constraint_str))
                                println("    ⚠️  WARNING: Constraint for $name contains slack variable terms!")
                                println("    Constraint: $constraint_str")
                            else
                                println("    ✓ Constraint for $name does NOT contain slack terms")
                            end
                        end
                    catch e
                        println("    Could not check constraint for $name: $e")
                    end
                end
            else
                println("    ⚠️  No 'dn' ramp constraint key found")
            end
        else
            println("    ⚠️  No ramp constraints found in container")
        end
        
    catch e
        println("ERROR checking slack variables: $e")
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

                            if ts_data !== nothing
                                ts_values = TimeSeries.values(ts_data)
                                ts_timestamps = TimeSeries.timestamp(ts_data)

                                # Add this load's contribution to each timestamp
                                # Time series already in MW (scaled by scaling_factor_multiplier)
                                for (i, ts_time) in enumerate(ts_timestamps)
                                    if ts_time in keys(load_by_time)
                                        load_by_time[ts_time] += abs(ts_values[i])
                                    end
                                end
                            else
                                # No time series, use static max load for all time steps
                                max_load = get_max_active_power(load)
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
        
        # AreaInterchange flows (inter-area transmission)
        try
            interchange_df = read_variable(results, FlowActivePowerVariable, AreaInterchange, table_format=TableFormat.LONG)
            if !isempty(interchange_df)
                for row in eachrow(interchange_df)
                    ai = get_component(AreaInterchange, sys, row.name)
                    from_area = get_name(get_from_area(ai))
                    to_area = get_name(get_to_area(ai))
                    # Create a descriptive name showing the flow direction
                    flow_name = "$(from_area) -> $(to_area)"
                    carrier = "interchange"
                    push!(dispatch_data, (DateTime=row.DateTime, name=flow_name, carrier=carrier, value=row.value))
                end
                println("  ✓ Exported $(nrow(interchange_df)) AreaInterchange flow records")
            end
        catch e
            println("  Could not read AreaInterchange flow: $e")
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
                theoretical_max = total_ts_max * 168
                println("Theoretical Max (if all at TS max for all timesteps): $(round(theoretical_max, digits=2)) MWh")
                if theoretical_max > 0
                    utilization_pct = (total_sienna / theoretical_max * 100)
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

