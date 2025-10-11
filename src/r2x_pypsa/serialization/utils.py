"""Utility functions for PyPSA to PSY serialization."""

from typing import Any
from loguru import logger
from r2x.api import System
from r2x.units import Voltage
from r2x.models import MinMax, FromTo_ToFrom, InputOutput

from infrasys.component import Component as PypsaDevice


def get_pypsa_property(system: System, component: PypsaDevice, property_name: str) -> Any:
    """Return the PSY compatible value for creating components.

    If the property has a time series it returns the maximum value of the time series.
    Otherwise returns the static property value.

    Parameters
    ----------
    system : System
        The system containing the component
    component : PypsaDevice
        The PyPSA component
    property_name : str
        Name of the property to extract

    Returns
    -------
    Any
        The property value, either static or max of time series
    """
    try:
        component_property = getattr(component, property_name)
        
        # Check if property has time series data
        if system.has_time_series(component, property_name):
            time_series = system.get_time_series(component, property_name)
            return float(max(time_series.data))
        
        # Handle different property types
        if hasattr(component_property, 'get_value'):
            # PypsaProperty object
            return component_property.get_value()
        else:
            # Direct value (string, float, etc.)
            return component_property
    except AttributeError:
        logger.warning(f"Property {property_name} not found on {component.name}")
        return None
    except Exception as e:
        logger.warning(f"Error extracting property {property_name} from {component.name}: {e}")
        return None


def convert_to_per_unit(value: float, base_value: float) -> float:
    """Convert a value to per unit based on base value.

    Parameters
    ----------
    value : float
        The value to convert
    base_value : float
        The base value for per unit conversion

    Returns
    -------
    float
        The value in per unit
    """
    if base_value == 0:
        return 0.0
    return value / base_value


def convert_voltage_units(value: float, from_units: str, to_units: str = "kV") -> float:
    """Convert voltage between different units.

    Parameters
    ----------
    value : float
        The voltage value to convert
    from_units : str
        Source units (e.g., "V", "kV")
    to_units : str
        Target units (e.g., "V", "kV")

    Returns
    -------
    float
        Converted voltage value
    """
    if from_units == to_units:
        return value
    
    # Convert to base unit (V) first
    if from_units == "kV":
        base_value = value * 1000
    elif from_units == "V":
        base_value = value
    else:
        logger.warning(f"Unknown voltage unit: {from_units}")
        return value
    
    # Convert to target unit
    if to_units == "kV":
        return base_value / 1000
    elif to_units == "V":
        return base_value
    else:
        logger.warning(f"Unknown target voltage unit: {to_units}")
        return base_value


def get_connected_bus(component: PypsaDevice, system: System) -> str | None:
    """Get the bus name that a component is connected to.

    Parameters
    ----------
    component : PypsaDevice
        The PyPSA component
    system : System
        The system containing the component

    Returns
    -------
    str | None
        The bus name or None if not found
    """
    # PyPSA components have bus references as strings
    if hasattr(component, 'bus'):
        return component.bus
    elif hasattr(component, 'bus0') and hasattr(component, 'bus1'):
        # For lines, we'll need to handle both buses
        return component.bus0, component.bus1
    else:
        logger.warning(f"Component {component.name} has no bus connection")
        return None


def create_voltage_from_pypsa(v_nom_value: float, v_nom_units: str = "kV") -> Voltage:
    """Create a Voltage object from PyPSA voltage data.

    Parameters
    ----------
    v_nom_value : float
        The nominal voltage value
    v_nom_units : str
        The voltage units

    Returns
    -------
    Voltage
        The Voltage object
    """
    # Convert to kV if needed
    if v_nom_units != "kV":
        v_nom_value = convert_voltage_units(v_nom_value, v_nom_units, "kV")
    
    return Voltage(v_nom_value, "kV")


def create_minmax_from_pypsa(min_value: float, max_value: float, base_value: float = 1.0) -> MinMax:
    """Create a MinMax object from PyPSA min/max values.

    Parameters
    ----------
    min_value : float
        Minimum value
    max_value : float
        Maximum value
    base_value : float
        Base value for per unit conversion

    Returns
    -------
    MinMax
        The MinMax object
    """
    return MinMax(
        min=convert_to_per_unit(min_value, base_value),
        max=convert_to_per_unit(max_value, base_value)
    )


def create_fromto_tofrom_from_pypsa(from_value: float, to_value: float, base_value: float = 1.0) -> FromTo_ToFrom:
    """Create a FromTo_ToFrom object from PyPSA flow values.

    Parameters
    ----------
    from_value : float
        From direction value
    to_value : float
        To direction value
    base_value : float
        Base value for per unit conversion

    Returns
    -------
    FromTo_ToFrom
        The FromTo_ToFrom object
    """
    return FromTo_ToFrom(
        from_to=convert_to_per_unit(from_value, base_value),
        to_from=convert_to_per_unit(to_value, base_value)
    )


def create_inputoutput_from_pypsa(input_value: float, output_value: float) -> InputOutput:
    """Create an InputOutput object from PyPSA efficiency values.

    Parameters
    ----------
    input_value : float
        Input efficiency (0-1)
    output_value : float
        Output efficiency (0-1)

    Returns
    -------
    InputOutput
        The InputOutput object
    """
    return InputOutput(
        input=input_value,
        output=output_value
    )


def get_pypsa_object_id(component: PypsaDevice) -> int | None:
    """Return the object id of a PyPSA component.

    Parameters
    ----------
    component : PypsaDevice
        The PyPSA component

    Returns
    -------
    int | None
        The object id or None if not found
    """
    if hasattr(component, "object_id"):
        return component.object_id
    return getattr(component, "ext", {}).get("object_id", None) if hasattr(component, "ext") else None
