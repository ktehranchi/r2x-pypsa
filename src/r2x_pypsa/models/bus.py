"""PyPSA Bus model for r2x-pypsa."""

from infrasys.component import Component
from typing import Annotated, Optional
from pydantic import Field

from .property_values import PypsaProperty, PropertyType
from .units import Units


class PypsaBus(Component):
    """PyPSA Bus component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    
    # Static attributes (Input)
    v_nom: Annotated[
        PropertyType,
        Units("kV"),
        Field(
            alias="Nominal Voltage",
            description="Nominal voltage",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0, units="kV")
    
    type: Annotated[
        PropertyType,
        Field(
            alias="Type",
            description="Placeholder for bus type. Not implemented.",
        ),
    ] = PypsaProperty.create(value=None)
    
    x: Annotated[
        PropertyType,
        Field(
            alias="Longitude",
            description="Longitude; the Spatial Reference System Identifier (SRID) is set in `n.srid`.",
        ),
    ] = PypsaProperty.create(value=0.0)
    
    y: Annotated[
        PropertyType,
        Field(
            alias="Latitude", 
            description="Latitude; the Spatial Reference System Identifier (SRID) is set in `n.srid`.",
        ),
    ] = PypsaProperty.create(value=0.0)
    
    carrier: Annotated[
        PropertyType,
        Field(
            alias="Carrier",
            description="Carrier, such as \"AC\", \"DC\", \"heat\" or \"gas\".",
        ),
    ] = PypsaProperty.create(value="AC")
    
    unit: Annotated[
        PropertyType,
        Field(
            alias="Unit",
            description="Unit of the bus' carrier if the implicitly assumed unit (\"MW\") is inappropriate (e.g. \"t/h\"). Only descriptive. Does not influence any PyPSA functions.",
        ),
    ] = PypsaProperty.create(value=None)
    
    location: Annotated[
        PropertyType,
        Field(
            alias="Location",
            description="Location of the bus. Does not influence the optimisation model but can be used for aggregation with `n.statistics`.",
        ),
    ] = PypsaProperty.create(value=None)
    
    v_mag_pu_min: Annotated[
        PropertyType,
        Field(
            alias="Minimum Voltage Per Unit",
            description="Minimum desired voltage, per unit of `v_nom`. Placeholder attribute not currently used by any functions.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0)
    
    v_mag_pu_max: Annotated[
        PropertyType,
        Field(
            alias="Maximum Voltage Per Unit",
            description="Maximum desired voltage, per unit of `v_nom`. Placeholder attribute not currently used by any functions.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'))
    
    # Time-varying attributes (can be static float or time series pd.Series)
    v_mag_pu_set: Annotated[
        PropertyType,
        Field(
            alias="Voltage Magnitude Set Point",
            description="Voltage magnitude set point, per unit of `v_nom`.",
        ),
    ] = PypsaProperty.create(value=1.0)
