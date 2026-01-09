# Converting to Sienna

This tutorial teaches you how to convert R2X Systems containing PyPSA components to Sienna/PowerSystems.jl format.

## What You'll Learn

- How to convert a full system to Sienna JSON format
- Understanding the output files
- How to use the converted system in Julia/Sienna

## Basic Conversion

After parsing a PyPSA network, convert it to Sienna format:

```python
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna

# Parse PyPSA network
parser = PypsaParser(netcdf_file="network.nc")
system = parser.build_system()

# Convert to Sienna format
pypsa_to_sienna(system, output_path="output/sienna_system")
```

## Output Files

The conversion produces two files:

1. **`sienna_system.json`** - System structure and component definitions
2. **`sienna_system_time_series.h5`** - Time series data in HDF5 format

## Conversion Options

The `pypsa_to_sienna` function accepts several options:

```python
pypsa_to_sienna(
    system,
    output_path="output/sienna_system",
    # Additional options as needed
)
```

## Using in Julia/Sienna

Load the converted system in Julia:

```julia
using PowerSystems

# Load the system
sys = System("output/sienna_system.json")

# Inspect components
println("Generators: ", length(get_components(Generator, sys)))
println("Buses: ", length(get_components(ACBus, sys)))

# Run economic dispatch
using PowerSimulations

# Create problem template
template = ProblemTemplate(NetworkModel(CopperPlatePowerModel))
set_device_model!(template, ThermalStandard, ThermalBasicED)
set_device_model!(template, RenewableDispatch, RenewableFullDispatch)

# Build and solve
problem = DecisionModel(template, sys; optimizer=optimizer_with_attributes(Gurobi.Optimizer))
build!(problem)
solve!(problem)
```

## Component Mapping

The conversion maps PyPSA components to Sienna types:

| PyPSA Component | Sienna Component |
|-----------------|------------------|
| Generator (thermal) | ThermalStandard |
| Generator (renewable) | RenewableDispatch |
| Generator (hydro) | HydroDispatch |
| StorageUnit | GenericBattery |
| Bus | ACBus |
| Load | PowerLoad |
| Line | ACBranch |
| Link | TwoTerminalHVDCLine |

## Verifying the Conversion

After conversion, verify the system loads correctly:

```python
import json

# Check the JSON structure
with open("output/sienna_system.json") as f:
    data = json.load(f)

print(f"System name: {data.get('name', 'N/A')}")
print(f"Components: {len(data.get('components', []))}")
```

## End-to-End Validation

For full validation comparing PyPSA and Sienna dispatch results, see the [Validating Dispatch](../how-to/validating-dispatch.md) guide.

## Next Steps

- Learn about [component mapping details](../explanation/component-mapping.md)
- See [how to validate dispatch results](../how-to/validating-dispatch.md)
