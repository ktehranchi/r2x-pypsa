"""PyPSA Link model for r2x-pypsa."""

from infrasys.component import Component
from typing import Annotated, Optional
from pydantic import Field

from .property_values import PypsaProperty, PropertyType
from .units import Units


class PypsaLink(Component):
    """PyPSA Link component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus0: str
    bus1: str
    
    # Static attributes (Input)
    type: Annotated[
        PropertyType,
        Field(
            alias="Type",
            description="Placeholder for link type. Not implemented.",
        ),
    ] = PypsaProperty.create(value=None)
    
    carrier: Annotated[
        PropertyType,
        Field(
            alias="Carrier",
            description="Carrier of the link describing its technology (e.g. gas boiler, electrolyser, HVDC link).",
        ),
    ] = PypsaProperty.create(value=None)
    
    active: Annotated[
        PropertyType,
        Field(
            alias="Active",
            description="Whether to consider the component in basic functionality or not",
        ),
    ] = PypsaProperty.create(value=True)
    
    build_year: Annotated[
        PropertyType,
        Field(
            alias="Build Year",
            description="Build year",
        ),
    ] = PypsaProperty.create(value=0)
    
    lifetime: Annotated[
        PropertyType,
        Units("years"),
        Field(
            alias="Lifetime",
            description="Lifetime",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="years")
    
    p_nom: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Nominal Power",
            description="Limit of power which can pass through link (in units of `bus0`). Ignored if `p_nom_extendable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_mod: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Nominal Power Module",
            description="Unit size of link module (e.g. fixed blocks of 100 MW).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_extendable: Annotated[
        PropertyType,
        Field(
            alias="Nominal Power Extendable",
            description="Switch to allow capacity `p_nom` to be extended.",
        ),
    ] = PypsaProperty.create(value=False)
    
    p_nom_min: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Minimum Nominal Power",
            description="If `p_nom_extendable=True`, set its minimum value.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_max: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Maximum Nominal Power",
            description="If `p_nom_extendable=True`, set its maximum value.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="MW")
    
    capital_cost: Annotated[
        PropertyType,
        Units("usd/MW"),
        Field(
            alias="Capital Cost",
            description="Fixed period costs of extending `p_nom` by 1 MW (unit of `bus0`), including periodized investment costs and periodic fixed O&M costs (e.g. annuitized investment costs). Any `length` factor must already be included here.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MW")
    
    length: Annotated[
        PropertyType,
        Units("km"),
        Field(
            alias="Length",
            description="Length of the link. Useful for calculating `capital_cost` for HVDC connections.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="km")
    
    terrain_factor: Annotated[
        PropertyType,
        Field(
            alias="Terrain Factor",
            description="Terrain factor for increasing `capital_cost` calculated from `length`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    committable: Annotated[
        PropertyType,
        Field(
            alias="Committable",
            description="Apply unit commitment constraints. This is only possible with `p_nom_extendable=False`.",
        ),
    ] = PypsaProperty.create(value=False)
    
    start_up_cost: Annotated[
        PropertyType,
        Units("usd"),
        Field(
            alias="Start Up Cost",
            description="Cost to start up the link. Only used if `committable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd")
    
    shut_down_cost: Annotated[
        PropertyType,
        Units("usd"),
        Field(
            alias="Shut Down Cost",
            description="Cost to shut down the link. Only used if `committable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd")
    
    min_up_time: Annotated[
        PropertyType,
        Field(
            alias="Minimum Up Time",
            description="Minimum number of snapshots for status to be 1. Only used if `committable=True`. Does not consider snapshot weightings.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0)
    
    min_down_time: Annotated[
        PropertyType,
        Field(
            alias="Minimum Down Time",
            description="Minimum number of snapshots for status to be 0. Only used if `committable=True`. Does not consider snapshot weightings.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0)
    
    up_time_before: Annotated[
        PropertyType,
        Field(
            alias="Up Time Before",
            description="Number of snapshots that the link was online before network.snapshots start. Only read if `committable=True` and `min_up_time>0`. Does not consider snapshot weightings.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1)
    
    down_time_before: Annotated[
        PropertyType,
        Field(
            alias="Down Time Before",
            description="Number of snapshots that the link was offline before network.snapshots start. Only read if `committable=True` and `min_down_time>0`. Does not consider snapshot weightings.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0)
    
    ramp_limit_start_up: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Start Up",
            description="Maximum increase at start up, per unit of `p_nom`. Only used if `committable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    ramp_limit_shut_down: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Shut Down",
            description="Maximum decrease at shut down, per unit of `p_nom`. Only used if `committable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    # Time-varying attributes (can be static float or time series pd.Series)
    efficiency: Annotated[
        PropertyType,
        Field(
            alias="Efficiency",
            description="Efficiency of energy transfer from `bus0` to `bus1`. Can be time-dependent (e.g. to represent temperature-dependent heat pump COP). Further efficiency attributes for further buses (e.g. `bus2`, `bus3`, etc.) are automatically expanded as needed (e.g. `efficiency2`, `efficiency3`, etc.).",
            ge=0,
            le=1,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    p_set: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Power Set Point",
            description="The dispatch set point for `p0` of the link (for optimisation and power flow).",
        ),
    ] = PypsaProperty.create(value=float('nan'), units="MW")
    
    p_min_pu: Annotated[
        PropertyType,
        Field(
            alias="Minimum Power Per Unit",
            description="Minimal dispatch per unit of `p_nom` for the link. Can also be negative.",
        ),
    ] = PypsaProperty.create(value=0.0)
    
    p_max_pu: Annotated[
        PropertyType,
        Field(
            alias="Maximum Power Per Unit",
            description="Maximal dispatch per unit of `p_nom` for the link. Can also be negative.",
        ),
    ] = PypsaProperty.create(value=1.0)
    
    marginal_cost: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Marginal Cost",
            description="Marginal cost of 1 MWh consumption from `bus0` (e.g. including variable operation and maintenance costs of an electrolyser but excluding electricity costs).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    marginal_cost_quadratic: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Quadratic Marginal Cost",
            description="Quadratic marginal cost for 1 MWh of consumption from `bus0`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    stand_by_cost: Annotated[
        PropertyType,
        Units("usd/h"),
        Field(
            alias="Stand By Cost",
            description="Stand-by cost for operating the link. This cost is incurred whenever the status is 1 (including when dispatch decision is zero).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/h")
    
    ramp_limit_up: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Up",
            description="Maximum increase from one snapshot to the next, per unit of `p_nom`. Ignored if NaN. Does not consider snapshot weightings.",
        ),
    ] = PypsaProperty.create(value=float('nan'))
    
    ramp_limit_down: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Down",
            description="Maximum decrease from one snapshot to the next, per unit of `p_nom`. Ignored if NaN. Does not consider snapshot weightings.",
        ),
    ] = PypsaProperty.create(value=float('nan'))
    
    # Output attributes (set by PyPSA functions)
    p_nom_opt: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Optimized Nominal Power",
            description="Optimised nominal capacity.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
