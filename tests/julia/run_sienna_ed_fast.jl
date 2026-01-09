#!/usr/bin/env julia
# Run Sienna Economic Dispatch (fast version - uses cached system)

# Activate local environment for reproducible package versions
import Pkg
Pkg.activate(@__DIR__)

using PowerSystems
using PowerSimulations
using Gurobi
using Dates
using Serialization

const PSY = PowerSystems
const PSI = PowerSimulations

# Get cache file and output file from command line args
system_cache_file = ARGS[1]
output_file = ARGS[2]

# Load prepared system and template from cache
println("Loading prepared system from: $system_cache_file")
sys, template = deserialize(system_cache_file)

# Create and solve model
println("Creating and solving optimization model...")
model = DecisionModel(
    template,
    sys;
    name = "ED",
    optimizer = optimizer_with_attributes(
        Gurobi.Optimizer, 
        "OutputFlag" => 1,
        "LogToConsole" => 1,
    ),
    system_to_file = false,
    resolution = Hour(1),
    initialize_model = false,
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

println("Objective: $objective")

