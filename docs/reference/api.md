# API Reference

Complete API documentation for r2x-pypsa.

## Parser Module

### PypsaParser

```{eval-rst}
.. automodule:: r2x_pypsa.parser
   :members:
   :undoc-members:
   :show-inheritance:
```

## Models Module

### Component Models

```{eval-rst}
.. automodule:: r2x_pypsa.models
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaGenerator

```{eval-rst}
.. autoclass:: r2x_pypsa.models.PypsaGenerator
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaBus

```{eval-rst}
.. autoclass:: r2x_pypsa.models.PypsaBus
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaLoad

```{eval-rst}
.. autoclass:: r2x_pypsa.models.PypsaLoad
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaStorageUnit

```{eval-rst}
.. autoclass:: r2x_pypsa.models.PypsaStorageUnit
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaLine

```{eval-rst}
.. autoclass:: r2x_pypsa.models.PypsaLine
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaLink

```{eval-rst}
.. autoclass:: r2x_pypsa.models.PypsaLink
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaStore

```{eval-rst}
.. autoclass:: r2x_pypsa.models.PypsaStore
   :members:
   :undoc-members:
   :show-inheritance:
```

### PypsaProperty

```{eval-rst}
.. autoclass:: r2x_pypsa.models.property_values.PypsaProperty
   :members:
   :undoc-members:
   :show-inheritance:
```

## Serialization Module

### Main API

```{eval-rst}
.. automodule:: r2x_pypsa.serialization.api
   :members:
   :undoc-members:
   :show-inheritance:
```

### PyPSA to PSY Conversion

```{eval-rst}
.. automodule:: r2x_pypsa.serialization.pypsa_to_psy
   :members:
   :undoc-members:
   :show-inheritance:
```

### Sienna Serialization

```{eval-rst}
.. automodule:: r2x_pypsa.serialization.to_sienna
   :members:
   :undoc-members:
   :show-inheritance:
```

### Cost Models

```{eval-rst}
.. automodule:: r2x_pypsa.serialization.cost_models
   :members:
   :undoc-members:
   :show-inheritance:
```

## Function Reference

### Parser Functions

#### PypsaParser

```python
class PypsaParser(netcdf_file=None, weather_year=None, network=None)
```

Parser for PyPSA networks to R2X System format.

**Parameters:**

- `netcdf_file` (str | Path, optional): Path to PyPSA netcdf file
- `weather_year` (int, optional): Custom weather year
- `network` (pypsa.Network, optional): Pre-loaded PyPSA network object

**Methods:**

- `build_system() -> System`: Build R2X System from PyPSA network

**Example:**

```python
from r2x_pypsa.parser import PypsaParser

# From file
parser = PypsaParser(netcdf_file="network.nc")
system = parser.build_system()

# From pre-loaded network
import pypsa
network = pypsa.Network("network.nc")
parser = PypsaParser(network=network)
system = parser.build_system()
```

### Serialization Functions

#### pypsa_to_sienna

```python
def pypsa_to_sienna(system, output_path, **kwargs)
```

Convert an R2X System containing PyPSA components to Sienna JSON/H5 format.

**Parameters:**

- `system` (System): R2X System with PyPSA components
- `output_path` (str | Path): Output path (without extension)
- `**kwargs`: Additional options

**Example:**

```python
from r2x_pypsa.serialization import pypsa_to_sienna

pypsa_to_sienna(system, output_path="output/sienna_system")
# Creates: output/sienna_system.json and output/sienna_system_time_series.h5
```

#### pypsa_to_psy

```python
def pypsa_to_psy(system) -> dict
```

Convert PyPSA components to PowerSystems.jl format.

**Parameters:**

- `system` (System): R2X System with PyPSA components

**Returns:**

- dict: PSY-formatted system data

### Model Helper Functions

#### get_ts_or_static

```python
def get_ts_or_static(network, df_name, attr_name, component_name, dense_df, static_data, default)
```

Get time series or static value for a component attribute.

**Parameters:**

- `network`: PyPSA network object
- `df_name`: Name of time-varying DataFrame (e.g., 'generators_t')
- `attr_name`: Attribute name (e.g., 'p_max_pu')
- `component_name`: Component name
- `dense_df`: Dense DataFrame from get_switchable_as_dense()
- `static_data`: Static data Series for the component
- `default`: Default value if not found

**Returns:**

- `PypsaProperty`: Property object with static value or time series

#### safe_float

```python
def safe_float(value, default=0.0) -> float
```

Safely convert a value to float, handling NaN and None.

#### safe_str

```python
def safe_str(value, default="") -> str
```

Safely convert a value to string, handling None.
