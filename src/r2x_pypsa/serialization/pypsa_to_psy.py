"""Convert PyPSA components to PowerSystems.jl components."""

from functools import singledispatch
from typing import Any

import pandas as pd
from loguru import logger
from r2x.api import Component, System
from r2x.enums import ACBusTypes, PrimeMoversType, StorageTechs, ThermalFuels
from r2x.models import (
    ACBus,
    Area,
    AreaInterchange,
    EnergyReservoirStorage,
    FromTo_ToFrom,
    Generator,
    HydroDispatch,
    InputOutput,
    MinMax,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    ThermalStandard,
    UpDown,
)
from r2x.units import Voltage

from infrasys.component import Component as PypsaDevice
from r2x_pypsa.models.bus import PypsaBus
from r2x_pypsa.models.generator import PypsaGenerator
from r2x_pypsa.models.line import PypsaLine
from r2x_pypsa.models.load import PypsaLoad
from r2x_pypsa.models.storage_unit import PypsaStorageUnit
from r2x_pypsa.models.store import PypsaStore
from r2x_pypsa.models.link import PypsaLink
from r2x_pypsa.serialization.cost_models import create_operational_cost
from r2x_pypsa.serialization.utils import (
    get_pypsa_property,
    convert_to_per_unit,
    create_voltage_from_pypsa,
    create_minmax_from_pypsa,
    create_updown_from_pypsa,
    create_fromto_tofrom_from_pypsa,
    create_inputoutput_from_pypsa,
    get_pypsa_object_id,
)


# Global counter for assigning unique object IDs to PyPSA components
_object_id_counter = {}


def create_single_time_series_from_pandas(ts_data, name: str):
    """Create a SingleTimeSeries from a pandas Series.
    
    Simplified approach similar to r2x-plexos - extract datetime info from index
    and use pandas' built-in methods.
    
    Parameters
    ----------
    ts_data : pd.Series
        Pandas Series with DatetimeIndex (or MultiIndex with datetime level)
    name : str
        Name for the time series
        
    Returns
    -------
    SingleTimeSeries
        A SingleTimeSeries object with proper initial_timestamp and resolution
    """
    from infrasys import SingleTimeSeries
    from datetime import timedelta, datetime
    import pandas as pd
    
    # Get the index - handle MultiIndex by extracting datetime level
    if isinstance(ts_data.index, pd.MultiIndex):
        # Find datetime level in MultiIndex
        for level_idx in range(ts_data.index.nlevels):
            level_values = ts_data.index.get_level_values(level_idx)
            if len(level_values) > 0 and pd.api.types.is_datetime64_any_dtype(level_values):
                index = level_values
                break
        else:
            # No datetime level found, use first level and try to convert
            index = ts_data.index.get_level_values(0)
            index = pd.to_datetime(index)
    else:
        index = ts_data.index
    
    # Extract initial_timestamp - pandas handles conversion
    if len(index) > 0:
        initial_timestamp = pd.to_datetime(index[0])
    else:
        initial_timestamp = datetime(2020, 1, 1)
    
    # Calculate resolution from index frequency or first two timestamps
    if len(index) > 1:
        # Try to infer frequency from index
        if hasattr(index, 'freq') and index.freq is not None:
            resolution = index.freq.delta
        else:
            # Calculate from first two timestamps
            resolution = pd.to_datetime(index[1]) - pd.to_datetime(index[0])
    else:
        # Default to 1 hour if only one timestamp
        resolution = timedelta(hours=1)
    
    # Convert pandas Timestamp to datetime if needed
    if isinstance(initial_timestamp, pd.Timestamp):
        initial_timestamp = initial_timestamp.to_pydatetime()
    
    # Convert timedelta if it's a pandas Timedelta
    if isinstance(resolution, pd.Timedelta):
        resolution = resolution.to_pytimedelta()
    
    # Normalize resolution to hours to ensure consistency
    # This prevents mixing Hour(1) and Millisecond(3600000) which causes errors
    if isinstance(resolution, timedelta):
        # Convert to total hours (as float) then back to timedelta to normalize
        total_hours = resolution.total_seconds() / 3600.0
        # Round to nearest hour to avoid floating point issues
        resolution = timedelta(hours=round(total_hours))
    
    return SingleTimeSeries.from_array(
        data=ts_data.values.tolist(),
        name=name,
        initial_timestamp=initial_timestamp,
        resolution=resolution,
    )


def get_or_assign_object_id(component: PypsaDevice, component_type: type) -> int:
    """Get existing object_id or assign a new unique one.
    
    Parameters
    ----------
    component : PypsaDevice
        The PyPSA component
    component_type : type
        The type of component (e.g., ACBus, ThermalStandard)
        
    Returns
    -------
    int
        A unique object ID
    """
    # Try to get existing object_id from component
    existing_id = get_pypsa_object_id(component)
    if existing_id:
        return existing_id
    
    # Generate new ID based on component type counter
    type_name = component_type.__name__
    if type_name not in _object_id_counter:
        _object_id_counter[type_name] = 0
    
    _object_id_counter[type_name] += 1
    return _object_id_counter[type_name]


@singledispatch
def pypsa_component_to_psy(
    component: PypsaDevice,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert PyPSA components to PowerSystems.jl components.

    Parameters
    ----------
    component : PypsaDevice
        The PyPSA component to convert
    pypsa_system : System
        R2X system with PyPSA components
    psy_system : System
        R2X system with PowerSystems.jl components
    mapping : dict[str, Any] | None
        Additional mapping configuration for translation
    """
    # Provide default mapping if none given
    if mapping is None:
        # Import here to avoid circular import
        from r2x_pypsa.serialization.api import create_default_mapping
        mapping = create_default_mapping()
    
    raise NotImplementedError(
        f"Conversion not implemented for {type(component).__name__}"
    )



@pypsa_component_to_psy.register
def _(
    component: PypsaBus,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert a PypsaBus to an ACBus."""
    if psy_system.list_components_by_name(ACBus, component.name):
        logger.trace("Component {} already processed. Skipping it.", component.name)
        return

    # Get or assign unique object_id
    object_id = get_or_assign_object_id(component, ACBus)

    # Extract voltage information
    v_nom = get_pypsa_property(pypsa_system, component, "v_nom")
    v_nom_units = "kV"  # PyPSA typically uses kV for voltage
    
    if v_nom is None or v_nom <= 0:
        logger.warning(f"Invalid voltage for bus {component.name}, using default 110 kV")
        v_nom = 110.0

    base_voltage = create_voltage_from_pypsa(v_nom, v_nom_units)

    # Determine bus type based on PyPSA bus type or default to PV
    # PowerSystems requires at least one REF (slack) bus
    existing_buses = list(psy_system.get_components(ACBus))
    has_ref_bus = any(bus.bustype == ACBusTypes.REF for bus in existing_buses)
    
    bustype = ACBusTypes.PV
    if hasattr(component, 'type') and component.type.get_value():
        bus_type_value = component.type.get_value()
        if bus_type_value == "Slack":
            bustype = ACBusTypes.REF
        elif bus_type_value == "PV":
            bustype = ACBusTypes.PV
        elif bus_type_value == "PQ":
            bustype = ACBusTypes.PQ
    
    # If no REF bus exists yet, make the first bus REF
    if not has_ref_bus and len(existing_buses) == 0:
        bustype = ACBusTypes.REF
        logger.info(f"Setting first bus {component.name} as REF (slack) bus")

    # Create or get Area for this bus (REQUIRED for AreaBalancePowerModel)
    # Area name follows pattern: {bus_name}_area (e.g., p60 -> p60_area)
    area_name = f"{component.name}_area"
    
    # Check if area already exists, create if not
    if not psy_system.list_components_by_name(Area, area_name):
        area = Area(name=area_name)
        psy_system.add_component(area)
        logger.debug(f"Created area {area_name} for bus {component.name}")
    else:
        area = psy_system.get_component(Area, area_name)
        logger.trace(f"Using existing area {area_name} for bus {component.name}")

    bus = ACBus(
        name=component.name,
        number=object_id,
        base_voltage=base_voltage,
        bustype=bustype,
        area=area,  # Assign area to bus (REQUIRED for AreaBalancePowerModel)
    )
    psy_system.add_component(bus)


@pypsa_component_to_psy.register
def _(
    component: PypsaGenerator,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert a PypsaGenerator to the appropriate Sienna generator type."""
    # Skip inactive generators
    active = get_pypsa_property(pypsa_system, component, "active")
    if active is False:
        logger.debug(f"Skipping inactive generator {component.name} (active=False)")
        return
    
    # Provide default mapping if none given
    if mapping is None:
        # Import here to avoid circular import
        from r2x_pypsa.serialization.api import create_default_mapping
        mapping = create_default_mapping()

    # Get generator type mappings
    generator_mapping = mapping.get("generator_mapping", {})
    prime_mover_mapping = mapping.get("prime_mover_mapping", {})
    fuel_mapping = mapping.get("fuel_mapping", {})

    # Determine generator type from carrier or category
    carrier = get_pypsa_property(pypsa_system, component, "carrier")
    if not carrier:
        # Check if it's renewable based on name or other attributes
        is_renewable = any(keyword in component.name.lower() for keyword in ['wind', 'solar', 'hydro', 'renewable'])
        gen_type = "renewable" if is_renewable else "thermal/other"
        logger.warning(f"Generator {component.name} ({gen_type}) has no carrier, skipping")
        return

    # Map carrier to generator class
    generator_model = generator_mapping.get(carrier, ThermalStandard)
    prime_mover = prime_mover_mapping.get(carrier, PrimeMoversType.OT)
    
    # Check if it's a renewable generator
    is_renewable = carrier in ['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'hydro', 'ror']
    gen_type = "renewable" if is_renewable else "thermal/other"

    # Find the bus for this generator
    bus_name = component.bus  # bus is a string attribute, not a PypsaProperty
    if not bus_name:
        logger.warning(f"{gen_type.capitalize()} generator {component.name} (carrier={carrier}) has no bus connection, skipping")
        return

    try:
        bus = psy_system.get_component(ACBus, bus_name)
    except Exception:
        logger.warning(f"Could not find bus {bus_name} for {gen_type} generator {component.name} (carrier={carrier}), skipping")
        return

    # Create generator with appropriate model
    generator = generator_model(
        uuid=component.uuid,
        name=component.name,
        bus=bus,
        prime_mover_type=prime_mover,
    )

    # Set fuel type for thermal generators
    if isinstance(generator, ThermalStandard) and carrier in fuel_mapping:
        generator.fuel = fuel_mapping[carrier]

    # Set operation cost
    if isinstance(generator, (ThermalStandard, RenewableDispatch)):
        generator.operation_cost = create_operational_cost(
            generator, component, pypsa_system
        )

    # Set capacity and limits
    p_nom = get_pypsa_property(pypsa_system, component, "p_nom")
    if p_nom is None or p_nom < 0:
        logger.warning(f"{gen_type.capitalize()} generator {component.name} (carrier={carrier}) has invalid capacity (p_nom={p_nom}), skipping")
        return
    elif p_nom == 0:
        logger.info(f"{gen_type.capitalize()} generator {component.name} (carrier={carrier}) has zero capacity, indicating future build. Skipping.")
        return

    # Get power limits
    # IMPORTANT: For p_max_pu, we need the STATIC value (nameplate = 1.0), not the time series mean/max (capacity factor)
    # The time series represents capacity factor over time, but the static limit should be nameplate capacity
    # NOTE: The parser sets p_max_pu.value to series.mean() when a time series exists, which is wrong for capacity limits
    # We need to use 1.0 (nameplate) if there's a time series, or the static value if no time series
    p_min_pu = get_pypsa_property(pypsa_system, component, "p_min_pu") or 0.0
    
    # Check if p_max_pu has a time series - if so, use 1.0 (nameplate) regardless of static value
    # If no time series, use the static value (or default to 1.0)
    p_max_pu_prop = getattr(component, "p_max_pu", None)
    if p_max_pu_prop is not None:
        # Check if there's a time series
        if hasattr(p_max_pu_prop, "has_time_series") and p_max_pu_prop.has_time_series():
            # Time series exists - use 1.0 (nameplate) for static limit
            # The time series itself will be used for dispatch constraints
            p_max_pu = 1.0
        elif hasattr(p_max_pu_prop, "value") and p_max_pu_prop.value is not None:
            # No time series - use static value
            p_max_pu = float(p_max_pu_prop.value)
        else:
            # No value set - default to 1.0
            p_max_pu = 1.0
    else:
        # No p_max_pu property - default to 1.0
        p_max_pu = 1.0

    # Use system-wide base_power (like loads use 100.0)
    # Do NOT set base_power = p_nom per-generator - base_power is system-wide for per-unitization
    # For RenewableDispatch, get_max_active_power() returns get_rating() * power_factor
    # get_rating() uses get_value() with Val(:mva), which multiplies by base_power when using NATURAL_UNITS
    # So: get_max_active_power() = rating * base_power * power_factor
    # To get p_nom MW, we need: rating = p_nom / base_power (in per-unit)
    # PyPSA's p_nom already represents the full cluster capacity (e.g., 2650 MW)
    # Use system-wide base_power for all generators
    generator.base_power = 100.0  # System-wide base power (MVA), not per-generator
    
    if isinstance(generator, RenewableDispatch):
        generator.rating = p_nom / 100.0  # Store rating in per-unit (relative to base_power)
        generator.power_factor = 1.0  # Power factor = 1.0 for full active power capability
    else:
        # For ThermalStandard and other generators, set rating and active_power_limits
        # rating is per-unit relative to base_power, so: rating = p_nom / base_power
        generator.rating = p_nom / 100.0  # Store rating in per-unit (relative to base_power)
        # active_power_limits should be in MW (not per-unit) according to PowerSystems.jl docs
        # But the JSON serialization might convert it, so we'll set it as per-unit relative to base_power for consistency
        generator.active_power_limits = create_minmax_from_pypsa(
            p_min_pu * p_nom, p_max_pu * p_nom, 100.0  # Use base_power (100.0) instead of p_nom
        )

    # Set ramping limits (convert from PyPSA per-unit per hour to Sienna per-unit per minute)
    # PyPSA: ramp_limit_up/down are per-unit per hour relative to p_nom (e.g., 1.0 = 100% of p_nom per hour)
    # Sienna: ramp_limits are in per-unit per minute relative to base_power (100 MVA)
    # Conversion: (ramp_limit_pu_per_hour * p_nom_mw / base_power_mva) / 60.0 min_per_hour
    #            = (ramp_limit_pu_per_hour * rating_pu) / 60.0 min_per_hour
    ramp_limit_up = get_pypsa_property(pypsa_system, component, "ramp_limit_up")
    ramp_limit_down = get_pypsa_property(pypsa_system, component, "ramp_limit_down")

    # Check if ramping limits are valid (not None and not NaN)
    if (ramp_limit_up is not None and not pd.isna(ramp_limit_up) and 
        ramp_limit_down is not None and not pd.isna(ramp_limit_down)):
        # Use p_nom / base_power directly for rating in per-unit (same as we set for generator.rating)
        rating_pu = p_nom / 100.0
        # Use helper function to create UpDown object, similar to create_minmax_from_pypsa
        generator.ramp_limits = create_updown_from_pypsa(
            float(ramp_limit_up), 
            float(ramp_limit_down), 
            rating_pu,
            base_value=100.0  # base_power for consistency
        )
        # Calculate expected ramp down in MW/h for verification
        expected_ramp_down_mw_per_h = ramp_limit_down * p_nom
        actual_ramp_down_mw_per_h = generator.ramp_limits.down * 100.0 * 60.0
        logger.debug(
            f"Set ramping limits for {component.name}: "
            f"up={generator.ramp_limits.up:.6f} pu/min, down={generator.ramp_limits.down:.6f} pu/min "
            f"(from PyPSA: up={ramp_limit_up:.6f} pu/h, down={ramp_limit_down:.6f} pu/h, "
            f"rating={rating_pu:.6f} pu, p_nom={p_nom:.2f} MW). "
            f"Expected ramp down: {expected_ramp_down_mw_per_h:.2f} MW/h, "
            f"Actual: {actual_ramp_down_mw_per_h:.2f} MW/h"
        )
    else:
        # No ramping limits (NaN for renewables, or missing)
        generator.ramp_limits = None
        logger.debug(
            f"Generator {component.name} has no ramping limits "
            f"(ramp_limit_up={ramp_limit_up}, ramp_limit_down={ramp_limit_down})"
        )

    # Set initial active power
    # Start thermal generators at full capacity (p_nom) to match PyPSA behavior
    # where generators can start at full power without ramp constraints
    # active_power must be in per-unit (relative to base_power) to match active_power_limits
    if isinstance(generator, ThermalStandard):
        # Start at full capacity - convert p_nom (MW) to per-unit
        # active_power should be in per-unit to match active_power_limits validation
        # rating = p_nom / base_power, so setting active_power = rating gives us full capacity
        rating_value = generator.rating.magnitude if hasattr(generator.rating, 'magnitude') else float(generator.rating)
        generator.active_power = rating_value  # Per-unit (full capacity = rating)
        # Set status to True so generator is considered "on" at start
        generator.status = True
        logger.debug(
            f"Set initial active_power={rating_value:.6f} pu (={rating_value * 100.0:.2f} MW) and status=True for {component.name}"
        )
    elif isinstance(generator, RenewableDispatch):
        # For renewable generators, start at 0 (they ramp up based on availability)
        # RenewableDispatch doesn't have a status attribute
        generator.active_power = 0.0
        logger.debug(
            f"Set initial active_power=0.0 pu for renewable {component.name}"
        )

    generator.services = []
    psy_system.add_component(generator)

    # Handle time series - extract from PypsaProperty if it exists
    # For renewable and hydro generators, p_max_pu is the capacity factor time series (per-unit 0-1)
    # PowerSimulations multiplies time series by get_max_active_power() to get MW
    # So store time series in per-unit (0-1), NOT in MW
    if hasattr(component, "p_max_pu"):
        if hasattr(component.p_max_pu, "has_time_series") and component.p_max_pu.has_time_series():
            ts_data = component.p_max_pu.get_time_series()
            
            # Keep time series in per-unit (0-1) - PowerSimulations will multiply by get_max_active_power()
            # get_max_active_power() = rating * base_power * power_factor = (p_nom / 100.0) * 100.0 * 1.0 = p_nom MW
            # So constraint will be: ts_value * p_nom = (p_max_pu * p_nom) which is correct
            ts = create_single_time_series_from_pandas(ts_data, "max_active_power")
            psy_system.add_time_series(ts, generator)
            logger.info(f"Added time series for generator {component.name} (length: {len(ts_data)}, stored in per-unit 0-1)")
        else:
            logger.debug(f"Generator {component.name} p_max_pu has no time series")


@pypsa_component_to_psy.register
def _(
    component: PypsaLine,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert a PypsaLine to an AreaInterchange."""
    # Get bus connections
    bus0_name = get_pypsa_property(pypsa_system, component, "bus0")
    bus1_name = get_pypsa_property(pypsa_system, component, "bus1")
    
    if not bus0_name or not bus1_name:
        logger.warning(f"Line {component.name} missing bus connections")
        return

    # Create areas for the buses
    from_area = Area(
        name=f"{bus0_name}_area",
        uuid=f"{bus0_name}_area_uuid"
    )
    to_area = Area(
        name=f"{bus1_name}_area", 
        uuid=f"{bus1_name}_area_uuid"
    )

    # Check if areas already exist
    if not psy_system.list_components_by_name(Area, from_area.name):
        psy_system.add_component(from_area)
    else:
        from_area = psy_system.get_component(Area, from_area.name)

    if not psy_system.list_components_by_name(Area, to_area.name):
        psy_system.add_component(to_area)
    else:
        to_area = psy_system.get_component(Area, to_area.name)

    # Check if interchange already exists
    existing_interchanges = psy_system.get_components(
        AreaInterchange,
        filter_func=lambda ai: (
            (ai.from_area == from_area and ai.to_area == to_area) or
            (ai.from_area == to_area and ai.to_area == from_area)
        )
    )
    if existing_interchanges:
        logger.trace("AreaInterchange already exists, skipping")
        return

    # Get flow limits
    s_nom = get_pypsa_property(pypsa_system, component, "s_nom")
    s_max_pu = get_pypsa_property(pypsa_system, component, "s_max_pu") or 1.0
    
    if s_nom is None or s_nom < 0:
        logger.warning(f"Line {component.name} has invalid capacity")
        return

    max_flow = s_nom * s_max_pu

    interchange = AreaInterchange(
        name=component.name,
        active_power_flow=0,
        from_area=from_area,
        to_area=to_area,
        flow_limits=FromTo_ToFrom(from_to=max_flow, to_from=max_flow),
    )
    interchange.services = []

    # NOTE: We do NOT add time series to AreaInterchange components
    # PowerSimulations requires ALL AreaInterchange components to have time series if ANY do,
    # and the time series must be named "from_to_flow_limit" and "to_from_flow_limit"
    # Since PyPSA lines typically have static capacities, we use static flow limits instead
    # This avoids the error: "No devices with time series from_to_flow_limit found"
    # Static flow limits are handled automatically by PowerSimulations when no time series exist

    psy_system.add_component(interchange)


@pypsa_component_to_psy.register
def _(
    component: PypsaLoad,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert a PypsaLoad to a PowerLoad."""
    # Get bus connection
    bus_name = get_pypsa_property(pypsa_system, component, "bus")
    if not bus_name:
        logger.warning(f"Load {component.name} has no bus connection")
        return

    try:
        bus = psy_system.get_component(ACBus, bus_name)
    except Exception:
        logger.warning(f"Could not find bus {bus_name} for load {component.name}")
        return

    # Use fixed base_power like r2x-plexos (100.0 MW)
    base_power = 100.0  # Fixed base power in MW
    
    # Extract max load value from time series or static value (in MW)
    # IMPORTANT: Get the raw time series data directly from PypsaProperty, not via get_pypsa_property
    # which might return the wrong value (mean instead of max, or already scaled)
    max_load_value_mw = 0.0
    has_ts = False
    
    if hasattr(component, "p_set"):
        try:
            if hasattr(component.p_set, "has_time_series") and component.p_set.has_time_series():
                has_ts = True
                ts_data = component.p_set.get_time_series()
                # Get max value from time series (time series is in MW from PyPSA)
                if hasattr(ts_data, 'max'):
                    max_load_value_mw = max(abs(ts_data.max()), abs(ts_data.min()))
                elif hasattr(ts_data, 'values'):
                    max_load_value_mw = max(abs(ts_data.values.max()), abs(ts_data.values.min()))
            else:
                # No time series - use static value
                if hasattr(component.p_set, "value") and component.p_set.value is not None:
                    max_load_value_mw = abs(float(component.p_set.value))
        except Exception as e:
            logger.warning(f"Could not extract load value for {component.name}: {e}")
            # Fallback to get_pypsa_property
            p_set = get_pypsa_property(pypsa_system, component, "p_set") or 0.0
            max_load_value_mw = abs(p_set) if isinstance(p_set, (int, float)) else 0.0
    
    # IMPORTANT: max_active_power static field should be stored in per-unit (relative to base_power)
    # When get_value() is called with NATURAL_UNITS, it multiplies by base_power to convert to MW
    # Documentation: "max_active_power = 1.0, # 10 MW per-unitized by device base_power"
    max_active_power_pu = max_load_value_mw / base_power if max_load_value_mw > 0 else 0.0  # Per-unit
    
    # Get active_power (static value) - use mean if time series exists, otherwise static value
    if has_ts and hasattr(component.p_set, "get_time_series"):
        try:
            ts_data = component.p_set.get_time_series()
            # Use mean for static active_power
            active_power_mw = float(ts_data.mean()) if hasattr(ts_data, 'mean') else 0.0
        except:
            active_power_mw = 0.0
    else:
        # No time series - use static value
        if hasattr(component.p_set, "value") and component.p_set.value is not None:
            active_power_mw = float(component.p_set.value)
        else:
            active_power_mw = 0.0
    
    active_power_pu = active_power_mw / base_power if active_power_mw != 0 else 0.0

    load = PowerLoad(
        name=component.name,
        bus=bus,
        base_power=base_power,  # Fixed 100.0 MW base
        active_power=active_power_pu,  # Per-unit
        reactive_power=1e-6,  # PowerSystems v5 requires > 0, use small positive value
        max_active_power=max_active_power_pu,  # Per-unit - get_value() multiplies by base_power to get MW
        max_reactive_power=1e-6,  # PowerSystems v5 requires > 0, use small positive value
    )
    load.services = []
    psy_system.add_component(load)

    # Handle time series - extract from PypsaProperty if it exists
    # Use "max_active_power" (default) - PowerSimulations StaticPowerLoad multiplies time series by get_max_active_power() (in MW),
    # so time series must be in per-unit (0-1) where 1.0 = max_active_power.
    # IMPORTANT: Store time series in per-unit (divide by max_active_power) - PowerSimulations will multiply by get_max_active_power() to get MW
    if hasattr(component, "p_set"):
        try:
            if hasattr(component.p_set, "has_time_series") and component.p_set.has_time_series():
                ts_data = component.p_set.get_time_series()
                # Convert to per-unit: divide by max_active_power (in MW)
                # PowerSimulations will multiply by get_max_active_power() to get back to MW
                if max_load_value_mw > 0:
                    if hasattr(ts_data, 'values'):
                        ts_data_pu = ts_data / max_load_value_mw
                    else:
                        import pandas as pd
                        ts_data_pu = pd.Series(ts_data.values / max_load_value_mw, index=ts_data.index)
                    ts = create_single_time_series_from_pandas(ts_data_pu, "max_active_power")
                    psy_system.add_time_series(ts, load)
                    logger.info(f"Added time series for load {component.name} (length: {len(ts_data)}, as 'max_active_power' in per-unit, max={max_load_value_mw} MW)")
                else:
                    logger.warning(f"Load {component.name} has zero max_load_value_mw, skipping time series")
            else:
                logger.debug(f"Load {component.name} p_set has no time series")
        except Exception as e:
            logger.warning(f"Could not extract time series from load {component.name}: {e}")


@pypsa_component_to_psy.register
def _(
    component: PypsaStorageUnit,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert a PypsaStorageUnit to an EnergyReservoirStorage.
    
    NOTE: If a corresponding PypsaStore exists with the same name, skip this conversion.
    The Store will be converted instead and will use this StorageUnit's power-side data
    (p_nom, efficiencies, time series) while using the Store's energy-side data (e_nom, e_initial, etc.).
    """
    # Skip inactive storage units
    active = get_pypsa_property(pypsa_system, component, "active")
    if active is False:
        logger.debug(f"Skipping inactive storage unit {component.name} (active=False)")
        return
    
    # Check if a corresponding Store exists - if so, skip StorageUnit conversion
    # The Store will handle the conversion and use StorageUnit's power-side data
    try:
        store = pypsa_system.get_component(PypsaStore, component.name)
        if store:
            logger.debug(
                f"StorageUnit {component.name} has corresponding Store, "
                f"skipping StorageUnit conversion (Store will be converted with StorageUnit's power limits)"
            )
            return
    except Exception:
        # No corresponding Store, proceed with StorageUnit conversion
        pass

    # Get bus connection
    bus_name = get_pypsa_property(pypsa_system, component, "bus")
    if not bus_name:
        logger.warning(f"Storage {component.name} has no bus connection")
        return

    try:
        bus = psy_system.get_component(ACBus, bus_name)
    except Exception:
        logger.warning(f"Could not find bus {bus_name} for storage {component.name}")
        return

    # Get storage parameters
    p_nom = get_pypsa_property(pypsa_system, component, "p_nom")
    max_hours = get_pypsa_property(pypsa_system, component, "max_hours") or 1.0
    efficiency_store = get_pypsa_property(pypsa_system, component, "efficiency_store") or 1.0
    efficiency_dispatch = get_pypsa_property(pypsa_system, component, "efficiency_dispatch") or 1.0
    state_of_charge_initial = get_pypsa_property(pypsa_system, component, "state_of_charge_initial") or 0.0
    cyclic_state_of_charge_per_period = get_pypsa_property(pypsa_system, component, "cyclic_state_of_charge_per_period") or False

    if p_nom is None or p_nom <= 0:
        logger.warning(f"Storage {component.name} has zero or invalid power capacity")
        return

    # Calculate storage capacity
    storage_capacity = p_nom * max_hours

    # Get power limits
    p_min_pu = get_pypsa_property(pypsa_system, component, "p_min_pu") or -1.0
    p_max_pu = get_pypsa_property(pypsa_system, component, "p_max_pu") or 1.0

    # System-wide base power (matching loads & renewables)
    base_power = 100.0  

    rating_pu = p_nom / base_power

    # Handle initial state of charge
    # For cyclic storage, PyPSA optimizes such that initial = final.
    # Try to get initial SOC from state_of_charge_set time series if available,
    # otherwise use state_of_charge_initial or a reasonable default.
    initial_storage_capacity_level = 0.0  # Default
    
    # Check for state_of_charge_set time series (set point, may indicate initial value)
    soc_from_ts = None
    try:
        if hasattr(component, 'state_of_charge_set'):
            soc_set_prop = getattr(component, 'state_of_charge_set')
            if hasattr(soc_set_prop, 'has_time_series') and soc_set_prop.has_time_series():
                soc_set_ts = soc_set_prop.get_time_series()
                if soc_set_ts is not None and len(soc_set_ts) > 0:
                    # Use first value from time series (in MWh)
                    soc_from_ts = float(soc_set_ts.iloc[0])
                    if not pd.isna(soc_from_ts) and soc_from_ts >= 0:
                        initial_storage_capacity_level = soc_from_ts / storage_capacity if storage_capacity > 0 else 0.0
                        logger.debug(
                            f"Storage {component.name} using first value from state_of_charge_set time series: "
                            f"{soc_from_ts:.2f} MWh ({initial_storage_capacity_level*100:.1f}% of capacity)"
                        )
    except Exception as e:
        logger.debug(f"Could not get state_of_charge_set time series for {component.name}: {e}")
    
    # If no time series available, use state_of_charge_initial or default
    if soc_from_ts is None or pd.isna(soc_from_ts):
        if cyclic_state_of_charge_per_period:
            # For cyclic storage, PyPSA ignores state_of_charge_initial and optimizes initial = final.
            # Use state_of_charge_initial if available, otherwise 50% as a reasonable default.
            if state_of_charge_initial > 0 and storage_capacity > 0:
                initial_storage_capacity_level = state_of_charge_initial / storage_capacity
                logger.debug(
                    f"Storage {component.name} has cyclic_state_of_charge_per_period=True, "
                    f"using state_of_charge_initial={state_of_charge_initial:.2f} MWh "
                    f"({initial_storage_capacity_level*100:.1f}% of capacity). "
                    f"Note: PyPSA will optimize such that initial = final during optimization."
                )
            else:
                initial_storage_capacity_level = 0.0
                logger.debug(
                    f"Storage {component.name} has cyclic_state_of_charge_per_period=True, "
                    f"using default initial SOC of 0% "
                    f"(state_of_charge_initial={state_of_charge_initial:.2f} MWh). "
                    f"Note: PyPSA will optimize such that initial = final during optimization."
                )
        else:
            # For non-cyclic storage, use the actual state_of_charge_initial value
            initial_storage_capacity_level = state_of_charge_initial / storage_capacity if storage_capacity > 0 else 0.0
            logger.debug(
                f"Storage {component.name} (non-cyclic) using state_of_charge_initial={state_of_charge_initial:.2f} MWh "
                f"({initial_storage_capacity_level*100:.1f}% of capacity)"
            )

    # IMPORTANT: Power limits must be in per-unit (relative to base_power) for PowerSystems.jl
    # PowerSystems.jl's get_input_active_power_limits() and get_output_active_power_limits()
    # multiply by base_power when NATURAL_UNITS is set, so we must set them in per-unit here.
    
    # Set storage_target for cyclic storage to enforce initial = final SOC
    # When energy_target=true in StorageDispatchWithReserves, this enforces final energy = storage_target
    # By setting storage_target = initial_storage_capacity_level, we get initial = final (cyclic constraint)
    if cyclic_state_of_charge_per_period:
        storage_target = initial_storage_capacity_level
        logger.debug(
            f"Storage {component.name} has cyclic_state_of_charge_per_period=True, "
            f"setting storage_target={storage_target:.4f} to match initial_storage_capacity_level "
            f"(will enforce initial = final SOC when energy_target=true)"
        )
    else:
        storage_target = 0.0  # Default: no target for non-cyclic storage
    
    battery = EnergyReservoirStorage(
        uuid=component.uuid,
        name=component.name,
        bus=bus,
        base_power=base_power,
        rating=rating_pu,     # per-unit (for rating field)
        initial_storage_capacity_level=initial_storage_capacity_level,
        efficiency=create_inputoutput_from_pypsa(efficiency_store, efficiency_dispatch),
        input_active_power_limits=MinMax(min=0.0, max=p_nom / base_power),   # per-unit (will be multiplied by base_power in NATURAL_UNITS)
        output_active_power_limits=MinMax(min=0.0, max=p_nom / base_power),  # per-unit (will be multiplied by base_power in NATURAL_UNITS)
        discharge_efficiency=efficiency_dispatch,
        storage_technology_type=StorageTechs.LIB,
        prime_mover_type=PrimeMoversType.BA,
        storage_capacity=storage_capacity / base_power,  # per-unit (will be multiplied by base_power in NATURAL_UNITS)
    )
    
    # NOTE: We do NOT set storage_target in ext dict here to avoid PowerSimulations bugs
    # Even when energy_target=false, PowerSimulations may try to read storage_target from JSON
    # and create StorageEnergySurplusVariable, causing dimension mismatch errors.
    # Instead, storage_target will only be set during serialization if energy_target=true is used.
    # For now, we skip setting it entirely to avoid the bug.
    # TODO: Re-enable this when PowerSimulations fixes the StorageEnergySurplusVariable dimension bug
    # if storage_target != 0.0 or cyclic_state_of_charge_per_period:
    #     battery.ext["storage_target"] = storage_target
    #     logger.debug(
    #         f"Set storage_target={storage_target:.4f} in ext dict for {component.name} "
    #         f"(will be serialized to JSON and used by Julia when energy_target=true)"
    #     )

    # Set operational cost
    battery.operation_cost = create_operational_cost(battery, component, pypsa_system)
    battery.services = []
    psy_system.add_component(battery)

    # Handle time series - extract from PypsaProperty
    for property_name in ["p_max_pu", "p_min_pu", "inflow"]:
        if hasattr(component, property_name):
            prop = getattr(component, property_name)
            if hasattr(prop, "has_time_series") and prop.has_time_series():
                ts_data = prop.get_time_series()
                if property_name == "p_max_pu":
                    ts = create_single_time_series_from_pandas(ts_data, "max_active_power")
                elif property_name == "p_min_pu":
                    ts = create_single_time_series_from_pandas(ts_data, "min_active_power")
                elif property_name == "inflow":
                    ts = create_single_time_series_from_pandas(ts_data, "inflow")
                else:
                    continue
                psy_system.add_time_series(ts, battery)
                logger.debug(f"Added {property_name} time series for storage {component.name}")


@pypsa_component_to_psy.register
def _(
    component: PypsaStore,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert a PypsaStore to an EnergyReservoirStorage."""
    # Skip inactive stores
    active = get_pypsa_property(pypsa_system, component, "active")
    if active is False:
        logger.debug(f"Skipping inactive store {component.name} (active=False)")
        return
    
    # Get bus connection
    bus_name = component.bus  # bus is a string attribute, not a PypsaProperty
    if not bus_name:
        logger.warning(f"Store {component.name} has no bus connection")
        return

    # Find the bus in the PSY system
    psy_bus = psy_system.get_component(ACBus, bus_name)
    if not psy_bus:
        logger.warning(f"Could not find bus {bus_name} for store {component.name}")
        return

    # Get store parameters (energy-side data)
    e_nom = get_pypsa_property(pypsa_system, component, "e_nom") or 0.0
    e_initial = get_pypsa_property(pypsa_system, component, "e_initial") or 0.0
    e_cyclic = get_pypsa_property(pypsa_system, component, "e_cyclic") or False
    e_cyclic_per_period = get_pypsa_property(pypsa_system, component, "e_cyclic_per_period") or False
    marginal_cost = get_pypsa_property(pypsa_system, component, "marginal_cost") or 0.0
    standing_loss = get_pypsa_property(pypsa_system, component, "standing_loss") or 0.0
    carrier = get_pypsa_property(pypsa_system, component, "carrier")
    
    if e_nom is None or e_nom < 0:
        logger.warning(f"Store {component.name} has invalid energy capacity")
        return

    # Check for corresponding StorageUnit (power-side data)
    # Store owns the energy buffer (e_nom), StorageUnit owns the power converter (p_nom, efficiencies)
    p_nom = e_nom  # Default: assume 1-hour discharge rate
    efficiency_store = 1.0
    efficiency_dispatch = 1.0
    storage_unit = None
    
    try:
        storage_unit = pypsa_system.get_component(PypsaStorageUnit, component.name)
        if storage_unit:
            # Use StorageUnit's power-side data
            p_nom = get_pypsa_property(pypsa_system, storage_unit, "p_nom") or 0.0
            # If StorageUnit has p_nom=0, skip this Store (can't charge/discharge, not dispatchable)
            if p_nom <= 0:
                logger.debug(
                    f"Store {component.name} has corresponding StorageUnit with p_nom={p_nom:.2f} MW, "
                    f"skipping Store conversion (no power capacity for dispatch)"
                )
                return
            efficiency_store = get_pypsa_property(pypsa_system, storage_unit, "efficiency_store") or 1.0
            efficiency_dispatch = get_pypsa_property(pypsa_system, storage_unit, "efficiency_dispatch") or 1.0
            logger.debug(
                f"Store {component.name} has corresponding StorageUnit, "
                f"using StorageUnit's p_nom={p_nom:.2f} MW, "
                f"efficiency_store={efficiency_store:.4f}, efficiency_dispatch={efficiency_dispatch:.4f}"
            )
    except Exception:
        # No corresponding StorageUnit, use defaults
        efficiency_store = 1.0 - standing_loss  # Convert standing loss to efficiency
        efficiency_dispatch = 1.0 - standing_loss
    
    # Calculate base_power and rating
    base_power = 100.0
    rating_pu = p_nom / base_power

    # Get initial state of charge from Store (energy-side data)
    # Priority: e_set time series > e_initial > default based on cyclic flags
    initial_storage_capacity_level = 0.0  # Default
    e_set_prop = None
    e_set_has_ts = False
    
    try:
        if hasattr(component, 'e_set'):
            e_set_prop = getattr(component, 'e_set')
            if hasattr(e_set_prop, 'has_time_series') and e_set_prop.has_time_series():
                e_set_ts = e_set_prop.get_time_series()
                if e_set_ts is not None and len(e_set_ts) > 0:
                    # Use first value from time series (in MWh)
                    initial_energy = float(e_set_ts.iloc[0])
                    if not pd.isna(initial_energy) and initial_energy >= 0:
                        initial_storage_capacity_level = initial_energy / e_nom if e_nom > 0 else 0.0
                        e_set_has_ts = True
                        logger.debug(
                            f"Store {component.name} using first value from e_set time series: "
                            f"{initial_energy:.2f} MWh ({initial_storage_capacity_level*100:.1f}% of capacity)"
                        )
    except Exception as e:
        logger.debug(f"Could not get e_set time series for {component.name}: {e}")
    
    # If no e_set time series, use e_initial or default based on cyclic flags
    if not e_set_has_ts:
        if e_cyclic or e_cyclic_per_period:
            # For cyclic storage, PyPSA optimizes initial = final.
            # Still use e_initial if it's set, otherwise default to 50%
            if e_initial > 0 and e_nom > 0:
                initial_storage_capacity_level = e_initial / e_nom
                logger.debug(
                    f"Store {component.name} has e_cyclic={e_cyclic} or e_cyclic_per_period={e_cyclic_per_period}, "
                    f"using e_initial={e_initial:.2f} MWh ({initial_storage_capacity_level*100:.1f}% of capacity)"
                )
            else:
                initial_storage_capacity_level = 0.0
                logger.debug(
                    f"Store {component.name} has e_cyclic={e_cyclic} or e_cyclic_per_period={e_cyclic_per_period}, "
                    f"no e_initial set, using default initial SOC of 0%"
                )
        else:
            # For non-cyclic, use e_initial
            initial_storage_capacity_level = e_initial / e_nom if e_nom > 0 else 0.0
            logger.debug(
                f"Store {component.name} (non-cyclic) using e_initial={e_initial:.2f} MWh "
                f"({initial_storage_capacity_level*100:.1f}% of capacity)"
            )

    # IMPORTANT: Power limits must be in per-unit (relative to base_power) for PowerSystems.jl
    # PowerSystems.jl's get_input_active_power_limits() and get_output_active_power_limits()
    # multiply by base_power when NATURAL_UNITS is set, so we must set them in per-unit here.
    # Use StorageUnit's efficiencies if available, otherwise use Store's standing_loss
    efficiency = InputOutput(
        input=efficiency_store,
        output=efficiency_dispatch
    )
    
    # Set storage_target for cyclic storage to enforce initial = final SOC
    # When energy_target=true in StorageDispatchWithReserves, this enforces final energy = storage_target
    # By setting storage_target = initial_storage_capacity_level, we get initial = final (cyclic constraint)
    if e_cyclic or e_cyclic_per_period:
        storage_target = initial_storage_capacity_level
        logger.debug(
            f"Store {component.name} has e_cyclic={e_cyclic} or e_cyclic_per_period={e_cyclic_per_period}, "
            f"setting storage_target={storage_target:.4f} to match initial_storage_capacity_level "
            f"(will enforce initial = final SOC when energy_target=true)"
        )
    else:
        storage_target = 0.0  # Default: no target for non-cyclic storage
    
    store = EnergyReservoirStorage(
        uuid=component.uuid,
        name=component.name,
        bus=psy_bus,
        base_power=base_power,
        rating=rating_pu,
        initial_storage_capacity_level=initial_storage_capacity_level,
        efficiency=efficiency,
        input_active_power_limits=MinMax(min=0.0, max=p_nom / base_power),   # per-unit (will be multiplied by base_power in NATURAL_UNITS)
        output_active_power_limits=MinMax(min=0.0, max=p_nom / base_power),  # per-unit (will be multiplied by base_power in NATURAL_UNITS)
        discharge_efficiency=efficiency_dispatch,
        storage_technology_type=StorageTechs.LIB,
        prime_mover_type=PrimeMoversType.BA,
        storage_capacity=e_nom / base_power,  # per-unit (will be multiplied by base_power in NATURAL_UNITS)
    )
    
    # NOTE: We do NOT set storage_target in ext dict here to avoid PowerSimulations bugs
    # Even when energy_target=false, PowerSimulations may try to read storage_target from JSON
    # and create StorageEnergySurplusVariable, causing dimension mismatch errors.
    # Instead, storage_target will only be set during serialization if energy_target=true is used.
    # For now, we skip setting it entirely to avoid the bug.
    # TODO: Re-enable this when PowerSimulations fixes the StorageEnergySurplusVariable dimension bug
    # if storage_target != 0.0 or e_cyclic or e_cyclic_per_period:
    #     store.ext["storage_target"] = storage_target
    #     logger.debug(
    #         f"Set storage_target={storage_target:.4f} in ext dict for {component.name} "
    #         f"(will be serialized to JSON and used by Julia when energy_target=true)"
    #     )
    store.services = []
    psy_system.add_component(store)

    # Set operation cost (temporarily disabled for testing)
    # if marginal_cost > 0:
    #     from r2x_pypsa.serialization.api import create_default_mapping
    #     if mapping is None:
    #         mapping = create_default_mapping()
    #     
    #     store.operation_cost = create_operational_cost(store, component, pypsa_system)

    # Add time series from Store (energy-side): e_set, marginal_cost
    for property_name in ["e_set", "marginal_cost"]:
        if hasattr(component, property_name):
            prop = getattr(component, property_name)
            if hasattr(prop, "has_time_series") and prop.has_time_series():
                ts_data = prop.get_time_series()
                if property_name == "e_set":
                    ts = create_single_time_series_from_pandas(ts_data, "energy_capacity")
                elif property_name == "marginal_cost":
                    ts = create_single_time_series_from_pandas(ts_data, "operation_cost")
                else:
                    continue
                psy_system.add_time_series(ts, store)
                logger.debug(f"Added {property_name} time series for store {component.name}")

    # Add time series from StorageUnit (power-side): p_max_pu, p_min_pu, inflow
    if storage_unit:
        for property_name in ["p_max_pu", "p_min_pu", "inflow"]:
            if hasattr(storage_unit, property_name):
                prop = getattr(storage_unit, property_name)
                if hasattr(prop, "has_time_series") and prop.has_time_series():
                    ts_data = prop.get_time_series()
                    if property_name == "p_max_pu":
                        ts = create_single_time_series_from_pandas(ts_data, "max_active_power")
                    elif property_name == "p_min_pu":
                        ts = create_single_time_series_from_pandas(ts_data, "min_active_power")
                    elif property_name == "inflow":
                        ts = create_single_time_series_from_pandas(ts_data, "inflow")
                    else:
                        continue
                    psy_system.add_time_series(ts, store)
                    logger.debug(f"Added {property_name} time series from StorageUnit for store {component.name}")


@pypsa_component_to_psy.register
def _(
    component: PypsaLink,
    pypsa_system: System,
    psy_system: System,
    mapping: dict[str, Any] | None = None,
):
    """Convert a PypsaLink to AreaInterchange objects.
    
    Logic: If lines exist, do not create area interchange objects.
    Else: create with forward and reverse links.
    """
    # Check if any lines exist in the system
    lines_exist = any(
        isinstance(comp, PypsaLine) 
        for comp in pypsa_system._component_mgr.iter_all()
    )
    
    if lines_exist:
        logger.trace(f"Lines exist in system, skipping link {component.name}")
        return
    
    # Get bus connections
    bus0_name = get_pypsa_property(pypsa_system, component, "bus0")
    bus1_name = get_pypsa_property(pypsa_system, component, "bus1")
    
    if not bus0_name or not bus1_name:
        logger.warning(f"Link {component.name} missing bus connections")
        return

    # Create areas for the buses
    from_area = Area(
        name=f"{bus0_name}_area",
    )
    to_area = Area(
        name=f"{bus1_name}_area", 
    )

    # Check if areas already exist
    if not psy_system.list_components_by_name(Area, from_area.name):
        psy_system.add_component(from_area)
    else:
        from_area = psy_system.get_component(Area, from_area.name)

    if not psy_system.list_components_by_name(Area, to_area.name):
        psy_system.add_component(to_area)
    else:
        to_area = psy_system.get_component(Area, to_area.name)

    # Get link parameters
    p_nom = get_pypsa_property(pypsa_system, component, "p_nom") or 0.0
    efficiency = get_pypsa_property(pypsa_system, component, "efficiency") or 1.0
    
    if p_nom < 0:
        logger.warning(f"Link {component.name} has invalid capacity")
        return

    # Create forward link (bus0 -> bus1)
    forward_interchange = AreaInterchange(
        name=f"{component.name}_forward",
        active_power_flow=0,
        from_area=from_area,
        to_area=to_area,
        flow_limits=FromTo_ToFrom(from_to=p_nom, to_from=p_nom * efficiency),
    )
    forward_interchange.services = []
    psy_system.add_component(forward_interchange)

    # Create reverse link (bus1 -> bus0)
    reverse_interchange = AreaInterchange(
        name=f"{component.name}_reverse",
        active_power_flow=0,
        from_area=to_area,
        to_area=from_area,
        flow_limits=FromTo_ToFrom(from_to=p_nom * efficiency, to_from=p_nom),
    )
    reverse_interchange.services = []
    psy_system.add_component(reverse_interchange)

    # NOTE: We do NOT add time series to AreaInterchange components from Links
    # PowerSimulations requires ALL AreaInterchange components to have time series if ANY do,
    # and the time series must be named "from_to_flow_limit" and "to_from_flow_limit"
    # Since PyPSA links typically have static capacities, we use static flow limits instead
    # This avoids the error: "No devices with time series from_to_flow_limit found"
    # Static flow limits are handled automatically by PowerSimulations when no time series exist
