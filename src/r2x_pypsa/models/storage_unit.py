"""PyPSA Storage Unit model for r2x-pypsa."""

from infrasys.component import Component
from typing import Annotated, Optional
from pydantic import Field

from .property_values import PypsaProperty, PropertyType
from .units import Units


class PypsaStorageUnit(Component):
    """PyPSA Storage Unit component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus: str
    
    # Static attributes (Input)
    control: Annotated[
        PropertyType,
        Field(
            alias="Control",
            description="P,Q,V control strategy for PF, must be \"PQ\", \"PV\" or \"Slack\".",
        ),
    ] = PypsaProperty.create(value="PQ")
    
    type: Annotated[
        PropertyType,
        Field(
            alias="Type",
            description="Placeholder for storage unit type. Not yet implemented.",
        ),
    ] = PypsaProperty.create(value=None)
    
    p_nom: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Nominal Power",
            description="Nominal power for limits on `p` in optimisation. Ignored if `p_nom_extendable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_mod: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Nominal Power Module",
            description="Nominal power of the storage unit module. Introduces integer variables if set.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_extendable: Annotated[
        PropertyType,
        Field(
            alias="Nominal Power Extendable",
            description="Switch to allow capacity `p_nom` to be extended in optimisation.",
        ),
    ] = PypsaProperty.create(value=False)
    
    p_nom_min: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Minimum Nominal Power",
            description="If `p_nom_extendable=True`, set the minimum value of `p_nom_opt`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_max: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Maximum Nominal Power",
            description="If `p_nom_extendable=True`, set the maximum value of `p_nom_opt`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="MW")
    
    sign: Annotated[
        PropertyType,
        Field(
            alias="Sign",
            description="Sign denoting the orientation of the dispatch variable.",
        ),
    ] = PypsaProperty.create(value=1.0)
    
    carrier: Annotated[
        PropertyType,
        Field(
            alias="Carrier",
            description="Prime mover energy carrier (e.g. coal, gas, wind, solar); required for global constraints on primary energy in optimisation",
        ),
    ] = PypsaProperty.create(value=None)
    
    capital_cost: Annotated[
        PropertyType,
        Units("usd/MW"),
        Field(
            alias="Capital Cost",
            description="Fixed period costs of extending `p_nom` by 1 MW, including periodized investment costs and periodic fixed O&M costs (e.g. annuitized investment costs).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MW")
    
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
    
    state_of_charge_initial: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Initial State of Charge",
            description="State of charge before the snapshots in the optimisation.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MWh")
    
    state_of_charge_initial_per_period: Annotated[
        PropertyType,
        Field(
            alias="Initial State of Charge Per Period",
            description="Switch: if True, the state of charge at the beginning of an investment period is set to `state_of_charge_initial`.",
        ),
    ] = PypsaProperty.create(value=False)
    
    cyclic_state_of_charge: Annotated[
        PropertyType,
        Field(
            alias="Cyclic State of Charge",
            description="Switch: if True, then `state_of_charge_initial` is ignored and the initial state of charge is set to the final state of charge for the group of snapshots in the optimisation (`soc[-1] = soc[len(snapshots)-1]`).",
        ),
    ] = PypsaProperty.create(value=False)
    
    cyclic_state_of_charge_per_period: Annotated[
        PropertyType,
        Field(
            alias="Cyclic State of Charge Per Period",
            description="Switch: if True, the cyclic constraints are applied to each investment period separately.",
        ),
    ] = PypsaProperty.create(value=True)
    
    max_hours: Annotated[
        PropertyType,
        Units("hours"),
        Field(
            alias="Maximum Hours",
            description="Maximum state of charge capacity in terms of hours at full output power capacity `p_nom`",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0, units="hours")
    
    # Time-varying attributes (can be static float or time series pd.Series)
    p_min_pu: Annotated[
        PropertyType,
        Field(
            alias="Minimum Power Per Unit",
            description="The minimum output for each snapshot per unit of `p_nom` for the optimisation. Negative sign implies storing mode withdrawing power from bus.",
        ),
    ] = PypsaProperty.create(value=-1.0)
    
    p_max_pu: Annotated[
        PropertyType,
        Field(
            alias="Maximum Power Per Unit",
            description="The maximum output for each snapshot per unit of `p_nom` for the optimisation. Positive sign implies discharging mode injecting power into bus.",
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
    
    p_dispatch_set: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Power Dispatch Set Point",
            description="Active power dispatch set point (for optimisation only)",
        ),
    ] = PypsaProperty.create(value=float('nan'), units="MW")
    
    p_store_set: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Power Store Set Point",
            description="Active power charging set point (for optimisation only)",
        ),
    ] = PypsaProperty.create(value=float('nan'), units="MW")
    
    spill_cost: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Spill Cost",
            description="Cost of spilling 1 MWh",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    marginal_cost: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Marginal Cost",
            description="Marginal cost of production (discharge) of 1 MWh.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    marginal_cost_quadratic: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Quadratic Marginal Cost",
            description="Quadratic marginal cost of production (discharge) of 1 MWh.",
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
    
    state_of_charge_set: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="State of Charge Set Point",
            description="State of charge set points for snapshots in the optimisation.",
        ),
    ] = PypsaProperty.create(value=float('nan'), units="MWh")
    
    efficiency_store: Annotated[
        PropertyType,
        Field(
            alias="Storage Efficiency",
            description="Efficiency of storage on the way into the storage.",
            ge=0,
            le=1,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    efficiency_dispatch: Annotated[
        PropertyType,
        Field(
            alias="Dispatch Efficiency",
            description="Efficiency of storage on the way out of the storage.",
            ge=0,
            le=1,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    standing_loss: Annotated[
        PropertyType,
        Field(
            alias="Standing Loss",
            description="Losses per hour to state of charge.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0)
    
    inflow: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Inflow",
            description="Inflow to the state of charge (e.g. due to river inflow in hydro reservoir).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    # Output attributes (set by PyPSA functions)
    p_nom_opt: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Optimized Nominal Power",
            description="Optimised nominal power.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
