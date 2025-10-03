"""PyPSA Load model for r2x-pypsa."""

from infrasys.component import Component
from typing import Annotated, Optional
from pydantic import Field

from .property_values import PypsaProperty, PropertyType
from .units import Units


class PypsaLoad(Component):
    """PyPSA Load component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus: str
    
    # Static attributes (Input)
    carrier: Annotated[
        PropertyType,
        Field(
            alias="Carrier",
            description="Carrier of the load.",
        ),
    ] = PypsaProperty.create(value=None)
    
    type: Annotated[
        PropertyType,
        Field(
            alias="Type",
            description="Placeholder for load type. Not implemented.",
        ),
    ] = PypsaProperty.create(value=None)
    
    sign: Annotated[
        PropertyType,
        Field(
            alias="Sign",
            description="Sign (opposite sign to generator)",
        ),
    ] = PypsaProperty.create(value=-1.0)
    
    active: Annotated[
        PropertyType,
        Field(
            alias="Active",
            description="Whether to consider the component in optimisation or not",
        ),
    ] = PypsaProperty.create(value=True)
    
    # Time-varying attributes (can be static float or time series pd.Series)
    p_set: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Power Set Point",
            description="Active power consumption (positive if the load is consuming power).",
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    q_set: Annotated[
        PropertyType,
        Field(
            alias="Reactive Power Set Point",
            description="Reactive power consumption (positive if the load is inductive).",
        ),
    ] = PypsaProperty.create(value=0.0, units="MVar")
