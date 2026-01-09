# Component Mapping

This document details how PyPSA components are mapped to Sienna/PowerSystems.jl types.

## Overview

The conversion from PyPSA to Sienna involves mapping components based on their carrier type and characteristics.

```{warning}
**Current Limitations**

r2x-pypsa currently only supports zonal transmission models. PyPSA `Link` components are converted to `AreaInterchange` objects. AC lines and HVDC lines are not yet fully supported for network-constrained dispatch.
```

## Generator Mapping

PyPSA generators are mapped based on their carrier attribute:

| PyPSA Carrier | Sienna Type | Notes |
|---------------|-------------|-------|
| `gas`, `coal`, `nuclear`, `oil`, `CCGT`, `OCGT` | `ThermalStandard` | Dispatchable thermal units |
| `solar`, `onwind`, `offwind`, `wind` | `RenewableDispatch` | Variable renewable energy |
| `hydro`, `ror` | `HydroDispatch` | Hydro with dispatch capability |

### Thermal Generator Conversion

```
PypsaGenerator (carrier=gas)     →    ThermalStandard
├── name                         →    name
├── bus                          →    bus (lookup ACBus)
├── p_nom                        →    base_power
├── p_min_pu × p_nom            →    active_power_limits.min
├── p_max_pu × p_nom            →    active_power_limits.max
├── marginal_cost               →    operation_cost.variable
├── start_up_cost               →    operation_cost.start_up
├── shut_down_cost              →    operation_cost.shut_down
├── ramp_limit_up               →    ramp_limits.up
├── ramp_limit_down             →    ramp_limits.down
├── min_up_time                 →    time_limits.up
└── min_down_time               →    time_limits.down
```

### Renewable Generator Conversion

```
PypsaGenerator (carrier=solar)   →    RenewableDispatch
├── name                         →    name
├── bus                          →    bus (lookup ACBus)
├── p_nom                        →    base_power
├── p_max_pu (time series)      →    max_active_power (time series)
└── marginal_cost               →    operation_cost (typically 0)
```

### Hydro Generator Conversion

```
PypsaGenerator (carrier=hydro)   →    HydroDispatch
├── name                         →    name
├── bus                          →    bus (lookup ACBus)
├── p_nom                        →    base_power
├── p_max_pu                    →    max_active_power
└── inflow                      →    inflow (time series)
```

## Storage Mapping

| PyPSA Component | Sienna Type | Notes |
|-----------------|-------------|-------|
| `StorageUnit` | `EnergyReservoirStorage` | Battery/pumped hydro |
| `Store` | `EnergyReservoirStorage` | Generic energy storage |

### Storage Unit Conversion

```
PypsaStorageUnit                 →    EnergyReservoirStorage
├── name                         →    name
├── bus                          →    bus (lookup ACBus)
├── p_nom                        →    input_active_power_limits.max
├── p_nom                        →    output_active_power_limits.max
├── max_hours × p_nom           →    storage_capacity
├── efficiency_store            →    efficiency.in
├── efficiency_dispatch         →    efficiency.out
├── state_of_charge_initial     →    initial_energy
└── inflow                      →    inflow (time series)
```

## Bus Mapping

| PyPSA Component | Sienna Type |
|-----------------|-------------|
| `Bus` | `ACBus` |

### Bus Conversion

```
PypsaBus                         →    ACBus
├── name                         →    name
├── v_nom                        →    base_voltage
├── x                           →    ext["x"] (longitude)
├── y                           →    ext["y"] (latitude)
└── carrier                     →    bustype (determines if AC/DC)
```

## Load Mapping

| PyPSA Component | Sienna Type |
|-----------------|-------------|
| `Load` | `PowerLoad` |

### Load Conversion

```
PypsaLoad                        →    PowerLoad
├── name                         →    name
├── bus                          →    bus (lookup ACBus)
└── p_set (time series)         →    max_active_power (time series)
```

## Transmission Mapping

### Current Implementation (Zonal)

PyPSA links representing inter-area transfers are converted to area interchange limits:

| PyPSA Component | Sienna Type | Notes |
|-----------------|-------------|-------|
| `Link` (inter-area) | `AreaInterchange` | Zonal transfer limits |

```
PypsaLink (bus0 in Area A, bus1 in Area B)  →  AreaInterchange
├── p_nom                                    →  flow_limits.from_to
├── p_nom                                    →  flow_limits.to_from
└── efficiency                               →  (applied to flow)
```

### Planned Implementation (Network)

Future versions will support:

| PyPSA Component | Sienna Type | Status |
|-----------------|-------------|--------|
| `Line` | `ACBranch` | Planned |
| `Link` (HVDC) | `TwoTerminalHVDCLine` | Planned |
| `Transformer` | `Transformer2W` | Planned |

## Cost Model Mapping

### Thermal Cost Models

```
PypsaGenerator                   →    ThermalGenerationCost
├── marginal_cost               →    variable.cost ($/MWh)
├── marginal_cost_quadratic     →    variable.cost (quadratic term)
├── start_up_cost               →    start_up ($/start)
├── shut_down_cost              →    shut_down ($/stop)
└── capital_cost                →    fixed ($/MW-year)
```

### Renewable Cost Models

```
PypsaGenerator (renewable)       →    RenewableCost
└── marginal_cost               →    variable (typically 0)
```

### Storage Cost Models

```
PypsaStorageUnit                 →    StorageCost
├── marginal_cost               →    variable ($/MWh discharged)
└── marginal_cost_storage       →    energy ($/MWh stored)
```

## Area and Zone Handling

PyPSA doesn't have explicit area definitions. r2x-pypsa can:

1. **Use bus location**: Group buses by geographic region
2. **Use carrier**: Group by bus carrier/type
3. **Single area**: Treat entire system as one zone (default)

For multi-area systems, buses are grouped and `Area` components are created in Sienna.

## Time Series Mapping

PyPSA time series are converted to Sienna `SingleTimeSeries`:

| PyPSA Attribute | Sienna Time Series |
|-----------------|-------------------|
| `generators_t.p_max_pu` | `max_active_power` on RenewableDispatch |
| `loads_t.p_set` | `max_active_power` on PowerLoad |
| `storage_units_t.inflow` | `inflow` on EnergyReservoirStorage |

Time series are stored in HDF5 format for efficient I/O.
