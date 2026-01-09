# Converting Systems

This guide covers how to convert R2X systems to different output formats.

## Convert to Sienna JSON

The primary use case is converting to Sienna/PowerSystems.jl format:

```python
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna

# Parse network
parser = PypsaParser(netcdf_file="network.nc")
system = parser.build_system()

# Convert to Sienna
pypsa_to_sienna(system, output_path="output/sienna_system")
```

This creates:
- `output/sienna_system.json` - System definition
- `output/sienna_system_time_series.h5` - Time series data

## Step-by-Step Conversion

For more control, use the lower-level API:

```python
from r2x_pypsa.serialization.api import pypsa_to_psy
from r2x_pypsa.serialization.to_sienna import infrasys_to_psy

# First convert PyPSA components to PSY format
psy_system = pypsa_to_psy(system)

# Then serialize to JSON/H5
infrasys_to_psy(psy_system, output_path="output/system")
```

## Converting Individual Components

Convert specific components:

```python
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.models import PypsaGenerator

# Get a generator
gen = next(system.get_components(PypsaGenerator))

# Convert to PSY component
psy_gen = pypsa_component_to_psy(gen, system)
```

## Output Directory Structure

After conversion, you'll have:

```
output/
├── sienna_system.json           # System definition
└── sienna_system_time_series.h5 # Time series data
```

## Verifying Output

Check the converted system:

```python
import json
import h5py

# Check JSON structure
with open("output/sienna_system.json") as f:
    data = json.load(f)
    print(f"Components: {len(data.get('components', []))}")

# Check time series
with h5py.File("output/sienna_system_time_series.h5", "r") as f:
    print(f"Time series datasets: {list(f.keys())}")
```

## Loading in Julia

Load the converted system in Julia:

```julia
using PowerSystems

sys = System("output/sienna_system.json")

# Verify components
for gen in get_components(Generator, sys)
    println(get_name(gen))
end
```
