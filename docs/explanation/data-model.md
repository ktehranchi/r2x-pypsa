# Data Model

This document explains how PyPSA components are represented in r2x-pypsa.

## PypsaProperty System

r2x-pypsa uses a flexible property system to handle both static values and time series data uniformly.

### PypsaProperty Class

Each attribute in a PyPSA component is wrapped in a `PypsaProperty` object:

```python
from r2x_pypsa.models.property_values import PypsaProperty

# Static value
p_nom = PypsaProperty.create(value=100.0, units="MW")

# Time series value
p_max_pu = PypsaProperty.create(
    value=0.0,  # Default
    time_series=pd.Series([0.8, 0.9, 0.7, ...]),
    units="pu"
)
```

### Property Features

- **Static or Time-Varying**: Same interface for both
- **Unit Tracking**: Optional units metadata
- **Min/Max Constraints**: Optional bounds
- **Pydantic Validation**: Type-safe with rich metadata

### Checking Property Type

```python
prop = generator.p_max_pu

if prop.is_time_series:
    data = prop.time_series
    print(f"Time series length: {len(data)}")
else:
    print(f"Static value: {prop.value}")
```

## Component Models

### PypsaGenerator

Represents all generator types (thermal, renewable, hydro):

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Unique identifier |
| `bus` | str | Connected bus name |
| `carrier` | PypsaProperty | Fuel/technology type |
| `p_nom` | PypsaProperty | Nominal power (MW) |
| `p_min_pu` | PypsaProperty | Minimum output (p.u.) |
| `p_max_pu` | PypsaProperty | Maximum output (p.u.) |
| `marginal_cost` | PypsaProperty | Variable cost ($/MWh) |
| `efficiency` | PypsaProperty | Conversion efficiency |
| `ramp_limit_up` | PypsaProperty | Ramp up limit (p.u./h) |
| `ramp_limit_down` | PypsaProperty | Ramp down limit (p.u./h) |
| `committable` | PypsaProperty | Unit commitment flag |
| `start_up_cost` | PypsaProperty | Start-up cost ($) |
| `shut_down_cost` | PypsaProperty | Shut-down cost ($) |
| `min_up_time` | PypsaProperty | Minimum up time (h) |
| `min_down_time` | PypsaProperty | Minimum down time (h) |

### PypsaBus

Represents electrical buses/nodes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Unique identifier |
| `v_nom` | PypsaProperty | Nominal voltage (kV) |
| `carrier` | PypsaProperty | AC or DC |
| `x` | PypsaProperty | Longitude coordinate |
| `y` | PypsaProperty | Latitude coordinate |
| `v_mag_pu_min` | PypsaProperty | Min voltage (p.u.) |
| `v_mag_pu_max` | PypsaProperty | Max voltage (p.u.) |

### PypsaStorageUnit

Represents battery and pumped hydro storage:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Unique identifier |
| `bus` | str | Connected bus name |
| `p_nom` | PypsaProperty | Power capacity (MW) |
| `max_hours` | PypsaProperty | Energy/power ratio (h) |
| `efficiency_store` | PypsaProperty | Charging efficiency |
| `efficiency_dispatch` | PypsaProperty | Discharging efficiency |
| `state_of_charge_initial` | PypsaProperty | Initial SOC (MWh) |
| `cyclic_state_of_charge` | PypsaProperty | Cyclic SOC flag |
| `marginal_cost` | PypsaProperty | Dispatch cost ($/MWh) |
| `inflow` | PypsaProperty | Natural inflow (MW) |

### PypsaLoad

Represents electrical demand:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Unique identifier |
| `bus` | str | Connected bus name |
| `p_set` | PypsaProperty | Active power demand (MW) |
| `carrier` | PypsaProperty | Load type |

### PypsaLine

Represents AC transmission lines:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Unique identifier |
| `bus0` | str | From bus |
| `bus1` | str | To bus |
| `s_nom` | PypsaProperty | Thermal limit (MVA) |
| `x` | PypsaProperty | Reactance (p.u.) |
| `r` | PypsaProperty | Resistance (p.u.) |
| `length` | PypsaProperty | Length (km) |

### PypsaLink

Represents DC links and controllable flows:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Unique identifier |
| `bus0` | str | From bus |
| `bus1` | str | To bus |
| `p_nom` | PypsaProperty | Transfer limit (MW) |
| `efficiency` | PypsaProperty | Transfer efficiency |
| `marginal_cost` | PypsaProperty | Flow cost ($/MWh) |

### PypsaStore

Represents energy storage without power constraints:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Unique identifier |
| `bus` | str | Connected bus name |
| `e_nom` | PypsaProperty | Energy capacity (MWh) |
| `e_initial` | PypsaProperty | Initial energy (MWh) |
| `standing_loss` | PypsaProperty | Self-discharge rate |

## Carrier Classification

PyPSA uses "carriers" to classify component types. r2x-pypsa maps these to Sienna component types:

### Thermal Carriers

```python
THERMAL_CARRIERS = ['gas', 'coal', 'nuclear', 'oil', 'lignite', 'CCGT', 'OCGT']
```

### Renewable Carriers

```python
RENEWABLE_CARRIERS = ['solar', 'onwind', 'offwind', 'wind', 'offwind_floating']
```

### Hydro Carriers

```python
HYDRO_CARRIERS = ['hydro', 'ror', 'PHS']  # ror = run-of-river
```

### Storage Carriers

```python
STORAGE_CARRIERS = ['battery', 'H2', 'Li-ion']
```

## Time Series Resolution

r2x-pypsa preserves the time resolution from PyPSA:

- Hourly data is most common
- Sub-hourly (15-min, 30-min) is supported
- Time series are aligned to a common initial time

The resolution is determined from the PyPSA network's snapshot index:

```python
resolution = network.snapshots[1] - network.snapshots[0]
```
