"""PyPSA Line model for r2x-pypsa."""

from infrasys.component import Component
from typing import Annotated, Optional
from pydantic import Field

from .property_values import PypsaProperty, PropertyType
from .units import Units


class PypsaLine(Component):
    """PyPSA Line component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus0: str
    bus1: str
    
    # Static attributes (Input)
    type: Annotated[
        PropertyType,
        Field(
            alias="Type",
            description="Name of line standard type. If this is not an empty string \"\", the line standard type impedance parameters are multiplied with the `length` and divided/multiplied by `num_parallel` to compute `x`, `r`, etc. This will override any values set in `r`, `x, and `b`. If the string is empty, values manually provided for `r`, `x`, etc. are taken.",
        ),
    ] = PypsaProperty.create(value=None)
    
    x: Annotated[
        PropertyType,
        Field(
            alias="Reactance",
            description="Series reactance, must be non-zero for AC branch for linearised power flow equations. If the line has series inductance $L$ in Henries then $x = 2\\pi f L$ where $f$ is the frequency in Hertz. Series impedance $z = r + jx$ must be non-zero for non-linear power flow calculations. Ignored if `type` defined.",
        ),
    ] = PypsaProperty.create(value=0.0, units="Ohm")
    
    r: Annotated[
        PropertyType,
        Field(
            alias="Resistance",
            description="Series resistance, must be non-zero for DC branch for linearised power flow equations. Series impedance $z = r + jx$ must be non-zero for the non-linear power flow. Ignored if `type` defined.",
        ),
    ] = PypsaProperty.create(value=0.0, units="Ohm")
    
    g: Annotated[
        PropertyType,
        Field(
            alias="Conductance",
            description="Shunt conductivity. Shunt admittance is $y = g + jb$.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="Siemens")
    
    b: Annotated[
        PropertyType,
        Field(
            alias="Susceptance",
            description="Shunt susceptance. If the line has shunt capacitance $C$ in Farads then $b = 2\\pi f C$ where $f$ is the frequency in Hertz. Shunt admittance is $y = g + jb$. Ignored if `type` defined.",
        ),
    ] = PypsaProperty.create(value=0.0, units="Siemens")
    
    s_nom: Annotated[
        PropertyType,
        Field(
            alias="Nominal Apparent Power",
            description="Limit of apparent power which can pass through branch in either direction. Ignored if `s_nom_extendable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MVA")
    
    s_nom_mod: Annotated[
        PropertyType,
        Field(
            alias="Nominal Apparent Power Module",
            description="Modular unit size of line expansion of ``s_nom`` (e.g. fixed rating of added circuit). Introduces integer variables.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MVA")
    
    s_nom_extendable: Annotated[
        PropertyType,
        Field(
            alias="Nominal Apparent Power Extendable",
            description="Switch to allow capacity `s_nom` to be extended in optimisation.",
        ),
    ] = PypsaProperty.create(value=False)
    
    s_nom_min: Annotated[
        PropertyType,
        Field(
            alias="Minimum Nominal Apparent Power",
            description="If `s_nom_extendable=True`, set the minimum value of `s_nom_opt`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MVA")
    
    s_nom_max: Annotated[
        PropertyType,
        Field(
            alias="Maximum Nominal Apparent Power",
            description="If `s_nom_extendable=True`, set the maximum value of `s_nom_opt`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="MVA")
    
    capital_cost: Annotated[
        PropertyType,
        Field(
            alias="Capital Cost",
            description="Fixed period costs of extending `s_nom` by 1 MVA, including periodized investment costs and periodic fixed O&M costs (e.g. annuitized investment costs). Any `length` factor must already be included here.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MVA")
    
    active: Annotated[
        PropertyType,
        Field(
            alias="Active",
            description="Whether to consider the component in optimisation or not",
        ),
    ] = PypsaProperty.create(value=True)
    
    build_year: Annotated[
        PropertyType,
        Field(
            alias="Build Year",
            description="Build year of line.",
        ),
    ] = PypsaProperty.create(value=0)
    
    lifetime: Annotated[
        PropertyType,
        Units("years"),
        Field(
            alias="Lifetime",
            description="Lifetime of line.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="years")
    
    length: Annotated[
        PropertyType,
        Units("km"),
        Field(
            alias="Length",
            description="Length of line used when `type` is set. Also useful for calculating `capital_cost`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="km")
    
    carrier: Annotated[
        PropertyType,
        Field(
            alias="Carrier",
            description="Type of current. \"AC\" is the only valid value for lines.",
        ),
    ] = PypsaProperty.create(value="AC")
    
    terrain_factor: Annotated[
        PropertyType,
        Field(
            alias="Terrain Factor",
            description="Terrain factor for increasing `length` for `capital_cost` calculation.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    num_parallel: Annotated[
        PropertyType,
        Field(
            alias="Number of Parallel",
            description="When `type` is set, this is the number of parallel circuits. Can also be fractional. If `type` is empty \"\" this value is ignored.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    v_ang_min: Annotated[
        PropertyType,
        Units("degrees"),
        Field(
            alias="Minimum Voltage Angle",
            description="Minimum voltage angle difference across the line. Placeholder attribute not currently used.",
        ),
    ] = PypsaProperty.create(value=float('-inf'), units="degrees")
    
    v_ang_max: Annotated[
        PropertyType,
        Units("degrees"),
        Field(
            alias="Maximum Voltage Angle",
            description="Maximum voltage angle difference across the line. Placeholder attribute not currently used.",
        ),
    ] = PypsaProperty.create(value=float('inf'), units="degrees")
    
    # Time-varying attributes (can be static float or time series pd.Series)
    s_max_pu: Annotated[
        PropertyType,
        Field(
            alias="Maximum Apparent Power Per Unit",
            description="The maximum allowed absolute apparent power flow per unit of `s_nom` for the optimisation (e.g. can set `s_max_pu<1` to approximate $N-1$ contingency factor, or can be time-varying to represent weather-dependent dynamic line rating for overhead lines).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
