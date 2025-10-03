"""PyPSA Store model for r2x-pypsa."""

from infrasys.component import Component
from typing import Annotated, Optional
from pydantic import Field

from .property_values import PypsaProperty, PropertyType
from .units import Units


class PypsaStore(Component):
    """PyPSA Store component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus: str
    
    # Static attributes (Input)
    type: Annotated[
        PropertyType,
        Field(
            alias="Type",
            description="Placeholder for store type. Not yet implemented.",
        ),
    ] = PypsaProperty.create(value=None)
    
    carrier: Annotated[
        PropertyType,
        Field(
            alias="Carrier",
            description="Carrier of the store.",
        ),
    ] = PypsaProperty.create(value=None)
    
    e_nom: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Nominal Energy",
            description="Nominal energy capacity (i.e. limit on `e`). Ignored if `e_nom_extendable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MWh")
    
    e_nom_mod: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Nominal Energy Module",
            description="Nominal energy capacity of the store module. Introduces integer variables if set.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MWh")
    
    e_nom_extendable: Annotated[
        PropertyType,
        Field(
            alias="Nominal Energy Extendable",
            description="Switch to allow capacity `e_nom` to be extended in optimisation.",
        ),
    ] = PypsaProperty.create(value=False)
    
    e_nom_min: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Minimum Nominal Energy",
            description="If `e_nom_extendable=True`, set the minimum value of `e_nom_opt`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MWh")
    
    e_nom_max: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Maximum Nominal Energy",
            description="If `e_nom_extendable=True`, set the maximum value of `e_nom_opt`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="MWh")
    
    e_initial: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Initial Energy",
            description="Energy before the snapshots in the optimisation.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MWh")
    
    e_initial_per_period: Annotated[
        PropertyType,
        Field(
            alias="Initial Energy Per Period",
            description="Switch: if True, then at the beginning of each investment period `e` is set to `e_initial`.",
        ),
    ] = PypsaProperty.create(value=False)
    
    e_cyclic: Annotated[
        PropertyType,
        Field(
            alias="Cyclic Energy",
            description="Switch: if True, then `e_initial` is ignored and the initial energy is set to the final energy for the group of snapshots in the optimisation.",
        ),
    ] = PypsaProperty.create(value=False)
    
    e_cyclic_per_period: Annotated[
        PropertyType,
        Field(
            alias="Cyclic Energy Per Period",
            description="Switch: if True, then the cyclic constraints are applied to each investment period separately.",
        ),
    ] = PypsaProperty.create(value=True)
    
    sign: Annotated[
        PropertyType,
        Field(
            alias="Sign",
            description="Sign denoting orientation of the energy variable (`e`).",
        ),
    ] = PypsaProperty.create(value=1.0)
    
    capital_cost: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Capital Cost",
            description="Fixed period costs of extending `e_nom` by 1 MWh, including periodized investment costs and periodic fixed O&M costs (e.g. annuitized investment costs).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
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
    
    # Time-varying attributes (can be static float or time series pd.Series)
    e_min_pu: Annotated[
        PropertyType,
        Field(
            alias="Minimum Energy Per Unit",
            description="Minimal value of `e` relative to `e_nom` for the optimisation.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0)
    
    e_max_pu: Annotated[
        PropertyType,
        Field(
            alias="Maximum Energy Per Unit",
            description="Maximal value of `e` relative to `e_nom` for the optimisation.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    p_set: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Power Set Point",
            description="Active power set point (for power flow only)",
        ),
    ] = PypsaProperty.create(value=float('nan'), units="MW")
    
    q_set: Annotated[
        PropertyType,
        Field(
            alias="Reactive Power Set Point",
            description="Reactive power set point (for power flow only)",
        ),
    ] = PypsaProperty.create(value=0.0, units="MVar")
    
    e_set: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Energy Set Point",
            description="Fixed energy filling level set point (for optimisation only)",
        ),
    ] = PypsaProperty.create(value=float('nan'), units="MWh")
    
    marginal_cost: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Marginal Cost",
            description="Marginal cost applied to both charging and discharging of 1 MWh.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    marginal_cost_quadratic: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Quadratic Marginal Cost",
            description="Quadratic marginal cost of applied to charging and discharging of 1 MWh.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    marginal_cost_storage: Annotated[
        PropertyType,
        Units("usd/MWh/h"),
        Field(
            alias="Marginal Cost Storage",
            description="Marginal cost of energy storage of 1 MWh for one hour.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh/h")
    
    standing_loss: Annotated[
        PropertyType,
        Field(
            alias="Standing Loss",
            description="Losses per hour to energy level.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0)
    
    # Output attributes (set by PyPSA functions)
    e_nom_opt: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Optimized Nominal Energy",
            description="Optimised nominal energy capacity outputed by optimisation.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MWh")
