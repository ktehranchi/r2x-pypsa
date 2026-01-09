"""
Julia test script to validate resource adequacy analysis using SiennaPRASInterface.

This test loads the serialized PowerSystems.jl system and runs a basic resource
adequacy assessment using PRAS (Probabilistic Resource Adequacy Suite).

The test demonstrates:
1. Loading a system from JSON
2. Converting to PRAS format using SiennaPRASInterface
3. Running Sequential Monte Carlo resource adequacy assessment
4. Evaluating basic reliability metrics (EUE, LOLE)
5. Generating plots and CSV outputs for validation

Usage:
    cd tests/julia
    julia --project=. test_resource_adequacy.jl
"""

using PowerSystems
using SiennaPRASInterface
using Test
using CSV
using DataFrames
using Plots
using Dates
using Statistics

# Aliases for convenience
const SPI = SiennaPRASInterface
const PSY = PowerSystems

# Output directory for results
const OUTPUT_DIR = joinpath(@__DIR__, "ra_test_output")

function setup_output_dir()
    """Create output directory if it doesn't exist."""
    if !isdir(OUTPUT_DIR)
        mkdir(OUTPUT_DIR)
        println("Created output directory: $OUTPUT_DIR")
    end
end

function find_system_file()
    """Find the PowerSystems.jl JSON file to use for testing."""
    # Try different potential locations
    potential_paths = [
        joinpath(@__DIR__, "..", "test_output", "test_network_1h_output_optimized.json"),
        joinpath(@__DIR__, "..", "test_output", "test_network_1h_comparison.json"),
        joinpath(@__DIR__, "..", "..", "test_output.json"),
    ]

    for path in potential_paths
        if isfile(path)
            return path
        end
    end

    error("No PowerSystems.jl JSON file found. Tried: $(potential_paths)")
end

function plot_hourly_shortfall(shortfalls, pras_sys; save_path=nothing)
    """Plot hourly shortfall across all samples."""
    # Sum shortfall across regions (if multiple)
    # shortfalls.shortfall is (n_regions, n_timestamps, n_samples)
    n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

    # Sum across regions to get total system shortfall
    total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)  # (n_timestamps, n_samples)

    # Calculate statistics across samples for each hour
    mean_shortfall = vec(mean(total_shortfall, dims=2))
    max_shortfall = vec(maximum(total_shortfall, dims=2))
    min_shortfall = vec(minimum(total_shortfall, dims=2))

    # Create hour labels (1 to n_timestamps)
    hours = 1:n_timestamps

    # Plot
    p = plot(
        hours, mean_shortfall,
        label="Mean Shortfall",
        xlabel="Hour",
        ylabel="Shortfall (MW)",
        title="Hourly System Shortfall ($(n_samples) samples)",
        linewidth=2,
        legend=:topright,
        size=(1200, 600),
    )

    # Add shaded region for min/max range
    plot!(p, hours, max_shortfall, fillrange=min_shortfall,
          alpha=0.3, label="Min-Max Range", color=:blue)

    if save_path !== nothing
        savefig(p, save_path)
        println("  Saved plot: $save_path")
    end

    return p
end

function plot_daily_shortfall(shortfalls; save_path=nothing)
    """Plot daily aggregated shortfall."""
    n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

    # Sum across regions
    total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)

    # Aggregate to daily (assuming hourly data, 24 hours per day)
    n_days = div(n_timestamps, 24)
    daily_shortfall = zeros(n_days, n_samples)

    for d in 1:n_days
        start_hr = (d - 1) * 24 + 1
        end_hr = d * 24
        if end_hr <= n_timestamps
            daily_shortfall[d, :] = sum(total_shortfall[start_hr:end_hr, :], dims=1)
        end
    end

    # Calculate statistics
    mean_daily = vec(mean(daily_shortfall, dims=2))
    max_daily = vec(maximum(daily_shortfall, dims=2))

    # Plot
    days = 1:n_days
    p = bar(
        days, mean_daily,
        label="Mean Daily Shortfall",
        xlabel="Day",
        ylabel="Shortfall (MWh)",
        title="Daily System Shortfall",
        legend=:topright,
        size=(1200, 600),
        alpha=0.7,
    )

    if save_path !== nothing
        savefig(p, save_path)
        println("  Saved plot: $save_path")
    end

    return p
end

function plot_lole_by_hour(shortfalls; save_path=nothing)
    """Plot probability of shortfall by hour of day."""
    n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

    # Sum across regions
    total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)

    # Calculate shortfall probability by hour of day (0-23)
    hours_of_day = 24
    shortfall_prob = zeros(hours_of_day)
    shortfall_count = zeros(hours_of_day)

    for t in 1:n_timestamps
        hour_of_day = mod(t - 1, 24) + 1  # 1 to 24
        for s in 1:n_samples
            if total_shortfall[t, s] > 0
                shortfall_count[hour_of_day] += 1
            end
        end
    end

    # Normalize by number of occurrences of each hour
    n_days = div(n_timestamps, 24)
    shortfall_prob = shortfall_count ./ (n_days * n_samples)

    # Plot
    p = bar(
        0:23, shortfall_prob,
        label="Shortfall Probability",
        xlabel="Hour of Day",
        ylabel="Probability",
        title="Loss of Load Probability by Hour of Day",
        legend=:topright,
        size=(800, 500),
        color=:red,
        alpha=0.7,
    )

    if save_path !== nothing
        savefig(p, save_path)
        println("  Saved plot: $save_path")
    end

    return p
end

function plot_eue_duration_magnitude(shortfalls; save_path=nothing)
    """
    Scatter plot of shortfall events with:
    - X-axis: Duration of shortfall event (hours)
    - Y-axis: Magnitude/size of shortfall (MW)

    Each point represents a shortfall event from the Monte Carlo samples.
    """
    n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

    # Sum across regions to get total system shortfall
    total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)  # (n_timestamps, n_samples)

    # Collect all shortfall events (duration, magnitude pairs)
    durations = Float64[]
    magnitudes = Float64[]

    # Process each sample to identify contiguous shortfall events
    for s in 1:n_samples
        sample_shortfall = total_shortfall[:, s]

        # Find contiguous shortfall events
        in_event = false
        event_start = 0
        event_max_mw = 0.0

        for t in 1:n_timestamps
            if sample_shortfall[t] > 0
                if !in_event
                    # Start new event
                    in_event = true
                    event_start = t
                    event_max_mw = sample_shortfall[t]
                else
                    # Continue event, track max magnitude
                    event_max_mw = max(event_max_mw, sample_shortfall[t])
                end
            else
                if in_event
                    # End event
                    duration = t - event_start
                    push!(durations, duration)
                    push!(magnitudes, event_max_mw)
                    in_event = false
                end
            end
        end

        # Handle event that extends to end of time series
        if in_event
            duration = n_timestamps - event_start + 1
            push!(durations, duration)
            push!(magnitudes, event_max_mw)
        end
    end

    if isempty(durations)
        println("  No shortfall events found - skipping EUE duration-magnitude plot")
        return nothing
    end

    # Create scatter plot
    p = scatter(
        durations, magnitudes,
        xlabel="Event Duration (hours)",
        ylabel="Peak Shortfall Magnitude (MW)",
        title="Shortfall Events: Duration vs Magnitude\n($(length(durations)) events from $(n_samples) samples)",
        label="Shortfall Event",
        markersize=6,
        markeralpha=0.6,
        markerstrokewidth=0,
        color=:red,
        size=(900, 600),
        legend=:topright,
    )

    # Add trend line if we have enough data points
    if length(durations) >= 3
        # Simple linear regression for trend
        mean_dur = mean(durations)
        mean_mag = mean(magnitudes)
        slope = sum((durations .- mean_dur) .* (magnitudes .- mean_mag)) / sum((durations .- mean_dur).^2)
        intercept = mean_mag - slope * mean_dur

        dur_range = range(minimum(durations), maximum(durations), length=100)
        plot!(p, dur_range, slope .* dur_range .+ intercept,
              label="Trend Line", linewidth=2, linestyle=:dash, color=:blue)
    end

    if save_path !== nothing
        savefig(p, save_path)
        println("  Saved plot: $save_path")
    end

    return p
end

function export_eue_events(shortfalls; save_path=nothing)
    """Export individual shortfall events with duration and magnitude to CSV."""
    n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

    # Sum across regions
    total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)

    # Collect event data
    events = DataFrame(
        Sample = Int[],
        EventID = Int[],
        StartHour = Int[],
        EndHour = Int[],
        Duration_hours = Int[],
        Peak_MW = Float64[],
        Total_MWh = Float64[],
    )

    for s in 1:n_samples
        sample_shortfall = total_shortfall[:, s]
        event_id = 0

        in_event = false
        event_start = 0
        event_max_mw = 0.0
        event_total_mwh = 0.0

        for t in 1:n_timestamps
            if sample_shortfall[t] > 0
                if !in_event
                    in_event = true
                    event_start = t
                    event_max_mw = sample_shortfall[t]
                    event_total_mwh = sample_shortfall[t]
                else
                    event_max_mw = max(event_max_mw, sample_shortfall[t])
                    event_total_mwh += sample_shortfall[t]
                end
            else
                if in_event
                    event_id += 1
                    push!(events, (
                        Sample = s,
                        EventID = event_id,
                        StartHour = event_start,
                        EndHour = t - 1,
                        Duration_hours = t - event_start,
                        Peak_MW = event_max_mw,
                        Total_MWh = event_total_mwh,
                    ))
                    in_event = false
                end
            end
        end

        # Handle event at end
        if in_event
            event_id += 1
            push!(events, (
                Sample = s,
                EventID = event_id,
                StartHour = event_start,
                EndHour = n_timestamps,
                Duration_hours = n_timestamps - event_start + 1,
                Peak_MW = event_max_mw,
                Total_MWh = event_total_mwh,
            ))
        end
    end

    if save_path !== nothing
        CSV.write(save_path, events)
        println("  Saved CSV: $save_path ($(nrow(events)) events)")
    end

    return events
end

function export_shortfall_summary(shortfall_stats, eue_result, lole_result; save_path=nothing)
    """Export summary statistics to CSV."""
    summary_df = DataFrame(
        Metric = [
            "EUE (MWh/year)",
            "EUE Standard Error (MWh)",
            "LOLE (hours/year)",
            "LOLE Standard Error (hours)",
        ],
        Value = [
            eue_result.eue.estimate,
            eue_result.eue.standarderror,
            lole_result.lole.estimate,
            lole_result.lole.standarderror,
        ],
    )

    if save_path !== nothing
        CSV.write(save_path, summary_df)
        println("  Saved CSV: $save_path")
    end

    return summary_df
end

function export_hourly_shortfall(shortfalls; save_path=nothing)
    """Export hourly shortfall data to CSV."""
    n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

    # Sum across regions
    total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)

    # Create DataFrame with hour column and sample columns
    df = DataFrame(Hour = 1:n_timestamps)

    for s in 1:n_samples
        df[!, Symbol("Sample_$s")] = total_shortfall[:, s]
    end

    # Add statistics columns
    df[!, :Mean] = vec(mean(total_shortfall, dims=2))
    df[!, :Max] = vec(maximum(total_shortfall, dims=2))
    df[!, :Min] = vec(minimum(total_shortfall, dims=2))
    df[!, :StdDev] = vec(std(total_shortfall, dims=2))

    if save_path !== nothing
        CSV.write(save_path, df)
        println("  Saved CSV: $save_path")
    end

    return df
end

function export_daily_shortfall(shortfalls; save_path=nothing)
    """Export daily aggregated shortfall to CSV."""
    n_regions, n_timestamps, n_samples = size(shortfalls.shortfall)

    # Sum across regions
    total_shortfall = dropdims(sum(shortfalls.shortfall, dims=1), dims=1)

    # Aggregate to daily
    n_days = div(n_timestamps, 24)
    daily_shortfall = zeros(n_days, n_samples)

    for d in 1:n_days
        start_hr = (d - 1) * 24 + 1
        end_hr = min(d * 24, n_timestamps)
        daily_shortfall[d, :] = sum(total_shortfall[start_hr:end_hr, :], dims=1)
    end

    # Create DataFrame
    df = DataFrame(Day = 1:n_days)

    for s in 1:n_samples
        df[!, Symbol("Sample_$s")] = daily_shortfall[:, s]
    end

    # Add statistics
    df[!, :Mean_MWh] = vec(mean(daily_shortfall, dims=2))
    df[!, :Max_MWh] = vec(maximum(daily_shortfall, dims=2))
    df[!, :Events] = vec(sum(daily_shortfall .> 0, dims=2))  # Number of samples with shortfall

    if save_path !== nothing
        CSV.write(save_path, df)
        println("  Saved CSV: $save_path")
    end

    return df
end

function export_generator_info(pras_sys; save_path=nothing)
    """Export generator information from PRAS system."""
    n_gens = length(pras_sys.generators.names)

    df = DataFrame(
        Generator = pras_sys.generators.names,
        Category = pras_sys.generators.categories,
    )

    # Add capacity info (first timestamp as representative)
    df[!, :Capacity_MW] = pras_sys.generators.capacity[:, 1]

    # Add outage parameters (λ = failure rate, μ = repair rate)
    df[!, :Lambda_FailureRate] = pras_sys.generators.λ[:, 1]
    df[!, :Mu_RepairRate] = pras_sys.generators.μ[:, 1]

    if save_path !== nothing
        CSV.write(save_path, df)
        println("  Saved CSV: $save_path")
    end

    return df
end

function run_resource_adequacy_test()
    """Main test function for resource adequacy analysis."""

    println("=" ^ 70)
    println("Resource Adequacy Test using SiennaPRASInterface")
    println("=" ^ 70)

    # Setup
    setup_output_dir()
    json_file = find_system_file()
    println("\nUsing system file: $json_file")

    @testset "Resource Adequacy Analysis" begin

        # Load system
        println("\n" * "-" ^ 50)
        println("Loading PowerSystems.jl System")
        println("-" ^ 50)

        sys = System(json_file)
        @test sys !== nothing
        println("✓ Successfully loaded system")

        # Set units to natural units (MW) for PRAS compatibility
        set_units_base_system!(sys, "NATURAL_UNITS")
        @test get_units_base(sys) == "NATURAL_UNITS"
        println("✓ Set system to NATURAL_UNITS")

        # Print system summary
        println("\nSystem Summary:")
        println("  Name: $(get_name(sys))")
        println("  Frequency: $(get_frequency(sys)) Hz")
        println("  Base Power: $(get_base_power(sys)) MVA")

        # Count components
        thermal_gens = collect(get_components(ThermalStandard, sys))
        hydro_gens = collect(get_components(HydroDispatch, sys))
        renewable_gens = collect(get_components(RenewableDispatch, sys))
        storage = collect(get_components(EnergyReservoirStorage, sys))
        loads = collect(get_components(PowerLoad, sys))
        lines = collect(get_components(Line, sys))
        areas = collect(get_components(Area, sys))

        println("\nComponent Counts:")
        println("  Thermal Generators: $(length(thermal_gens))")
        println("  Hydro Generators: $(length(hydro_gens))")
        println("  Renewable Generators: $(length(renewable_gens))")
        println("  Storage Units: $(length(storage))")
        println("  Loads: $(length(loads))")
        println("  Lines: $(length(lines))")
        println("  Areas: $(length(areas))")

        # Build PRAS system
        println("\n" * "-" ^ 50)
        println("Building PRAS System")
        println("-" ^ 50)

        # Build device model list based on available components
        device_models = [
            DeviceRAModel(
                PowerSystems.ThermalStandard,
                GeneratorPRAS(max_active_power="max_active_power"),
            ),
            DeviceRAModel(
                PowerSystems.HydroGen,
                GeneratorPRAS(max_active_power="max_active_power"),
            ),
            DeviceRAModel(
                PowerSystems.EnergyReservoirStorage,
                EnergyReservoirSoC(),
            ),
            DeviceRAModel(
                PowerSystems.RenewableGen,
                GeneratorPRAS(max_active_power="max_active_power"),
            ),
            DeviceRAModel(
                PowerSystems.PowerLoad,
                StaticLoadPRAS(max_active_power="max_active_power"),
            ),
        ]

        # Only add Line and AreaInterchange models if lines exist
        if length(lines) > 0
            push!(device_models, DeviceRAModel(PowerSystems.Line, LinePRAS()))
            push!(device_models, DeviceRAModel(PowerSystems.AreaInterchange, AreaInterchangeLimit()))
            println("  Including Line and AreaInterchange models ($(length(lines)) lines found)")
        else
            println("  Skipping Line/AreaInterchange models (no lines in system)")
        end

        # Define the RA problem template
        problem_template = RATemplate(PowerSystems.Area, device_models)

        # Convert to PRAS system
        pras_sys = generate_pras_system(sys, problem_template)

        # Print PRAS system info
        println("\nPRAS System Information:")
        println("  Generators: $(length(pras_sys.generators.names))")
        println("  Regions: $(length(pras_sys.regions.names))")
        println("  Timestamps: $(size(pras_sys.generators.capacity, 2))")

        if length(pras_sys.regions.names) > 0
            println("  Region names: $(pras_sys.regions.names)")
        end

        # Export generator info
        export_generator_info(pras_sys, save_path=joinpath(OUTPUT_DIR, "pras_generators.csv"))

        # Run Resource Adequacy Assessment
        println("\n" * "-" ^ 50)
        println("Running Sequential Monte Carlo Assessment")
        println("-" ^ 50)

        # Use more samples for better statistics
        n_samples = 50
        method = SequentialMonteCarlo(
            samples=n_samples,
            seed=42,
            verbose=true,
            threaded=false,
        )

        println("  Samples: $n_samples")
        println("  Seed: 42")
        println("  Running simulation...")

        shortfalls, shortfall_stats = assess(pras_sys, method, ShortfallSamples(), Shortfall())

        @test shortfalls !== nothing
        @test shortfall_stats !== nothing
        println("✓ Resource adequacy assessment completed")

        # Calculate reliability metrics
        eue_result = EUE(shortfall_stats)
        lole_result = LOLE(shortfall_stats)

        println("\n" * "-" ^ 50)
        println("Reliability Metrics")
        println("-" ^ 50)
        println("  EUE (Expected Unserved Energy): $(round(eue_result.eue.estimate, digits=2)) MWh/year")
        println("  EUE Standard Error: $(round(eue_result.eue.standarderror, digits=2)) MWh")
        println("  LOLE (Loss of Load Expectation): $(round(lole_result.lole.estimate, digits=4)) hours/year")
        println("  LOLE Standard Error: $(round(lole_result.lole.standarderror, digits=4)) hours")

        # Sanity checks
        @test eue_result.eue.estimate >= 0
        @test lole_result.lole.estimate >= 0
        @test size(shortfalls.shortfall, 3) == n_samples

        # Export results to CSV
        println("\n" * "-" ^ 50)
        println("Exporting Results to CSV")
        println("-" ^ 50)

        export_shortfall_summary(
            shortfall_stats, eue_result, lole_result,
            save_path=joinpath(OUTPUT_DIR, "ra_summary_statistics.csv")
        )

        export_hourly_shortfall(
            shortfalls,
            save_path=joinpath(OUTPUT_DIR, "hourly_shortfall.csv")
        )

        export_daily_shortfall(
            shortfalls,
            save_path=joinpath(OUTPUT_DIR, "daily_shortfall.csv")
        )

        # Export event-level data
        export_eue_events(
            shortfalls,
            save_path=joinpath(OUTPUT_DIR, "shortfall_events.csv")
        )

        # Generate plots
        println("\n" * "-" ^ 50)
        println("Generating Plots")
        println("-" ^ 50)

        plot_hourly_shortfall(
            shortfalls, pras_sys,
            save_path=joinpath(OUTPUT_DIR, "hourly_shortfall.png")
        )

        plot_daily_shortfall(
            shortfalls,
            save_path=joinpath(OUTPUT_DIR, "daily_shortfall.png")
        )

        plot_lole_by_hour(
            shortfalls,
            save_path=joinpath(OUTPUT_DIR, "lole_by_hour.png")
        )

        # Scatter plot of EUE: Duration (hours) vs Magnitude (MW)
        plot_eue_duration_magnitude(
            shortfalls,
            save_path=joinpath(OUTPUT_DIR, "eue_duration_vs_magnitude.png")
        )

        println("\n" * "=" ^ 70)
        println("✓ All resource adequacy tests passed!")
        println("  Results saved to: $OUTPUT_DIR")
        println("=" ^ 70)
    end
end

# Run the test
if abspath(PROGRAM_FILE) == @__FILE__
    run_resource_adequacy_test()
end
