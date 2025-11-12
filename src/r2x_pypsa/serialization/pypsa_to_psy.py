"""Convert PyPSA components to PowerSystems.jl components."""

from functools import singledispatch
from typing import Any

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


@singledispatch
def pypsa_component_to_psy_additions(
    component: Component,
    pypsa_system: System,
    psy_system: System,
):
    """Create new PowerSystems.jl components to match PyPSA model.

    Parameters
    ----------
    component : PypsaDevice
        The PyPSA component to convert
    pypsa_system : System
        R2X system with PyPSA components
    psy_system : System
        R2X system with PowerSystems.jl components
    """
    return


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

    bus = ACBus(
        name=component.name,
        number=object_id,
        base_voltage=base_voltage,
        bustype=bustype,
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
        logger.warning(f"Generator {component.name} has no carrier, skipping")
        return

    # Map carrier to generator class
    generator_model = generator_mapping.get(carrier, ThermalStandard)
    prime_mover = prime_mover_mapping.get(carrier, PrimeMoversType.OT)

    # Find the bus for this generator
    bus_name = component.bus  # bus is a string attribute, not a PypsaProperty
    if not bus_name:
        logger.warning(f"Generator {component.name} has no bus connection")
        return

    try:
        bus = psy_system.get_component(ACBus, bus_name)
    except Exception:
        logger.warning(f"Could not find bus {bus_name} for generator {component.name}")
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
    if isinstance(generator, (ThermalStandard, HydroDispatch, RenewableDispatch)):
        generator.operation_cost = create_operational_cost(
            generator, component, pypsa_system
        )

    # Set capacity and limits
    p_nom = get_pypsa_property(pypsa_system, component, "p_nom")
    if p_nom is None or p_nom < 0:
        logger.warning(f"Generator {component.name} has invalid capacity")
        return
    elif p_nom == 0:
        logger.info(f"Generator {component.name} has zero capacity, indicating future build.")
        return

    # Get power limits
    p_min_pu = get_pypsa_property(pypsa_system, component, "p_min_pu") or 0.0
    p_max_pu = get_pypsa_property(pypsa_system, component, "p_max_pu") or 1.0

    generator.base_power = p_nom
    generator.active_power_limits = create_minmax_from_pypsa(
        p_min_pu * p_nom, p_max_pu * p_nom, p_nom
    )

    generator.services = []
    psy_system.add_component(generator)

    # Handle time series - extract from PypsaProperty if it exists
    # For renewable generators, p_max_pu is the capacity factor time series (per-unit 0-1)
    # Convert to MW by multiplying by p_nom (like r2x-plexos converts rating_factor to MW)
    if hasattr(component, "p_max_pu"):
        if hasattr(component.p_max_pu, "has_time_series") and component.p_max_pu.has_time_series():
            ts_data = component.p_max_pu.get_time_series()
            # Convert capacity factor (per-unit) to MW
            if hasattr(ts_data, 'values'):
                ts_data_mw = ts_data * p_nom
            else:
                import pandas as pd
                ts_data_mw = pd.Series(ts_data.values * p_nom, index=ts_data.index)
            ts = create_single_time_series_from_pandas(ts_data_mw, "max_active_power")
            psy_system.add_time_series(ts, generator)
            logger.info(f"Added time series for generator {component.name} (length: {len(ts_data)}, converted to MW)")
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

    # Add time series if they exist - extract from PypsaProperty
    if hasattr(component, "s_max_pu") and component.s_max_pu.has_time_series():
        ts_data = component.s_max_pu.get_time_series()
        ts = create_single_time_series_from_pandas(ts_data, "max_active_power")
        psy_system.add_time_series(ts, interchange)
        logger.debug(f"Added time series for line {component.name}")

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

    # Get load value (in MW)
    p_set = get_pypsa_property(pypsa_system, component, "p_set") or 0.0
    
    # Use fixed base_power like r2x-plexos (100.0 MW)
    base_power = 100.0  # Fixed base power in MW
    
    # Check if there's a time series to determine max load value
    # Time series will be converted to per-unit later, so we need max in MW for static field
    has_ts = False
    max_load_value_mw = abs(p_set) if isinstance(p_set, (int, float)) else 0.0
    
    if hasattr(component, "p_set"):
        try:
            if hasattr(component.p_set, "has_time_series") and component.p_set.has_time_series():
                has_ts = True
                ts_data = component.p_set.get_time_series()
                # Get max value from time series (in MW)
                if hasattr(ts_data, 'max'):
                    max_load_value_mw = max(abs(ts_data.max()), abs(ts_data.min()), abs(p_set) if isinstance(p_set, (int, float)) else 0.0)
                elif hasattr(ts_data, 'values'):
                    max_load_value_mw = max(abs(ts_data.values.max()), abs(ts_data.values.min()), abs(p_set) if isinstance(p_set, (int, float)) else 0.0)
        except Exception as e:
            logger.warning(f"Could not check time series for load {component.name}: {e}")
    
    # IMPORTANT: max_active_power static field should be stored in per-unit (relative to base_power)
    # When get_value() is called with NATURAL_UNITS, it multiplies by base_power to convert to MW
    # Documentation: "max_active_power = 1.0, # 10 MW per-unitized by device base_power"
    max_active_power_pu = max_load_value_mw / base_power if max_load_value_mw > 0 else 0.0  # Per-unit
    active_power_pu = (p_set / base_power) if isinstance(p_set, (int, float)) and p_set != 0 else 0.0

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
    # Use "active_power" instead of "max_active_power" to avoid PowerSystems v5 bug where
    # get_max_active_power() returns MW instead of per-unit when a time series named "max_active_power" exists.
    # PowerSimulations StaticPowerLoad will still use this time series for constraints.
    if hasattr(component, "p_set"):
        try:
            if hasattr(component.p_set, "has_time_series") and component.p_set.has_time_series():
                ts_data = component.p_set.get_time_series()
                # Convert to per-unit (divide by base_power)
                # Store as "active_power" (not "max_active_power") to avoid PowerSystems v5 bug
                if hasattr(ts_data, 'values'):
                    ts_data_pu = ts_data / base_power
                else:
                    import pandas as pd
                    ts_data_pu = pd.Series(ts_data.values / base_power, index=ts_data.index)
                ts = create_single_time_series_from_pandas(ts_data_pu, "active_power")
                psy_system.add_time_series(ts, load)
                logger.info(f"Added time series for load {component.name} (length: {len(ts_data)}, as 'active_power' in per-unit)")
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
    """Convert a PypsaStorageUnit to an EnergyReservoirStorage."""
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

    if p_nom is None or p_nom < 0:
        logger.warning(f"Storage {component.name} has invalid power capacity")
        return

    # Calculate storage capacity
    storage_capacity = p_nom * max_hours

    # Get power limits
    p_min_pu = get_pypsa_property(pypsa_system, component, "p_min_pu") or -1.0
    p_max_pu = get_pypsa_property(pypsa_system, component, "p_max_pu") or 1.0

    battery = EnergyReservoirStorage(
        uuid=component.uuid,
        name=component.name,
        bus=bus,
        base_power=max(p_nom, 0.001),
        initial_storage_capacity_level=state_of_charge_initial / storage_capacity if storage_capacity > 0 else 0.0,
        efficiency=create_inputoutput_from_pypsa(efficiency_store, efficiency_dispatch),
        input_active_power_limits=MinMax(min=0, max=p_nom),
        output_active_power_limits=MinMax(min=0, max=p_nom),
        discharge_efficiency=efficiency_dispatch,
        storage_technology_type=StorageTechs.LIB,
        prime_mover_type=PrimeMoversType.BA,
        storage_capacity=storage_capacity,
    )

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

    # Get store parameters
    e_nom = get_pypsa_property(pypsa_system, component, "e_nom") or 0.0
    marginal_cost = get_pypsa_property(pypsa_system, component, "marginal_cost") or 0.0
    standing_loss = get_pypsa_property(pypsa_system, component, "standing_loss") or 0.0
    carrier = get_pypsa_property(pypsa_system, component, "carrier")
    
    if e_nom is None or e_nom < 0:
        logger.warning(f"Store {component.name} has invalid energy capacity")
        return

    # Create the energy reservoir storage
    # For stores, we assume 1-hour charge/discharge rate
    p_nom = e_nom  # Assume 1-hour discharge rate
    efficiency = 1.0 - standing_loss  # Convert standing loss to efficiency
    
    store = EnergyReservoirStorage(
        uuid=component.uuid,
        name=component.name,
        bus=psy_bus,
        base_power=max(p_nom, 0.001),
        initial_storage_capacity_level=0.5,  # Default to 50% initial charge
        efficiency=InputOutput(input=efficiency, output=efficiency),
        input_active_power_limits=MinMax(min=0, max=p_nom),
        output_active_power_limits=MinMax(min=0, max=p_nom),
        discharge_efficiency=efficiency,
        storage_technology_type=StorageTechs.LIB,  # Default to lithium-ion battery
        prime_mover_type=PrimeMoversType.BA,
        storage_capacity=e_nom,
    )
    store.services = []
    psy_system.add_component(store)

    # Set operation cost (temporarily disabled for testing)
    # if marginal_cost > 0:
    #     from r2x_pypsa.serialization.api import create_default_mapping
    #     if mapping is None:
    #         mapping = create_default_mapping()
    #     
    #     store.operation_cost = create_operational_cost(store, component, pypsa_system)

    # Add time series if they exist - extract from PypsaProperty
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

    # Add time series if they exist - extract from PypsaProperty
    for property_name in ["p_set", "marginal_cost"]:
        if hasattr(component, property_name):
            prop = getattr(component, property_name)
            if hasattr(prop, "has_time_series") and prop.has_time_series():
                ts_data = prop.get_time_series()
                if property_name == "p_set":
                    ts = create_single_time_series_from_pandas(ts_data, "active_power")
                elif property_name == "marginal_cost":
                    ts = create_single_time_series_from_pandas(ts_data, "operation_cost")
                else:
                    continue
                # Add time series to both forward and reverse interchanges
                psy_system.add_time_series(ts, forward_interchange)
                psy_system.add_time_series(ts, reverse_interchange)
                logger.debug(f"Added {property_name} time series for link {component.name}")
