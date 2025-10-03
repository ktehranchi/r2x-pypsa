"""PyPSA Generator model for r2x-pypsa."""

from infrasys.component import Component
from typing import Annotated
from pydantic import Field

from r2x_pypsa.models.property_values import PypsaProperty, PropertyType
from r2x_pypsa.models.units import Units


class PypsaGenerator(Component):
    """PyPSA Generator component with all standard PyPSA attributes."""

    # Required attributes
    name: str  # Unique name
    bus: str   # Name of bus to which generator is attached
    
    # Static attributes with Pydantic field specifications
    control: Annotated[
        PropertyType,
        Field(
            alias="Control",
            description="P,Q,V control strategy for power flow, must be \"PQ\", \"PV\" or \"Slack\". Only relevant for \"AC\" and \"DC\" buses.",
            json_schema_extra={"enum": ["PQ", "PV", "Slack"]},
        ),
    ] = PypsaProperty.create(value="PQ")
    
    type: Annotated[
        PropertyType,
        Field(
            alias="Type",
            description="Placeholder for generator type. Not implemented.",
        ),
    ] = PypsaProperty.create(value=None)
    
    p_nom: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Nominal Power",
            description="Nominal power for limits on `p` in optimization. Ignored if `p_nom_extendable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_mod: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Nominal Power Module",
            description="Nominal power of the generator module (e.g. fixed unit size of a nuclear power plant). Introduces integer variables if set.",
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_extendable: Annotated[
        PropertyType,
        Field(
            alias="Nominal Power Extendable",
            description="Switch to allow capacity `p_nom` to be extended in optimization.",
        ),
    ] = PypsaProperty.create(value=False)
    
    p_nom_min: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Minimum Nominal Power",
            description="If `p_nom` is extendable in optimization, set its minimum value.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    p_nom_max: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Maximum Nominal Power",
            description="If `p_nom` is extendable in optimization, set its maximum value (e.g. limited by technical potential).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="MW")
    
    e_sum_min: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Minimum Energy Sum",
            description="The minimum total energy produced during a single optimization horizon.",
        ),
    ] = PypsaProperty.create(value=float('-inf'), units="MWh")
    
    e_sum_max: Annotated[
        PropertyType,
        Units("MWh"),
        Field(
            alias="Maximum Energy Sum",
            description="The maximum total energy produced during a single optimization horizon.",
        ),
    ] = PypsaProperty.create(value=float('inf'), units="MWh")
    
    sign: Annotated[
        PropertyType,
        Field(
            alias="Sign",
            description="Sign denoting the orientation of the dispatch variable (e.g. positive for generation, negative for consumption).",
            json_schema_extra={"enum": [1.0, -1.0]},
        ),
    ] = PypsaProperty.create(value=1.0)
    
    carrier: Annotated[
        PropertyType,
        Field(
            alias="Carrier",
            description="Prime mover energy carrier (e.g. coal, gas, wind, solar); required for global constraints on primary energy in optimisation",
        ),
    ] = PypsaProperty.create(value=None)
    
    active: Annotated[
        PropertyType,
        Field(
            alias="Active",
            description="Whether to consider the component in optimization or not",
        ),
    ] = PypsaProperty.create(value=True)
    
    build_year: Annotated[
        PropertyType,
        Field(
            alias="Build Year",
            description="Build year of the generator.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0)
    
    lifetime: Annotated[
        PropertyType,
        Units("yr"),
        Field(
            alias="Lifetime",
            description="Lifetime of the generator.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=float('inf'), units="yr")
    
    capital_cost: Annotated[
        PropertyType,
        Units("usd/MW"),
        Field(
            alias="Capital Cost",
            description="Fixed period costs of extending `p_nom` by 1 MW, including periodized investment costs and periodic fixed O&M costs (e.g. annuitized investment costs).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MW")
    
    # Unit commitment attributes
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
            description="Cost to start up the generator. Only used if `committable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd")
    
    shut_down_cost: Annotated[
        PropertyType,
        Units("usd"),
        Field(
            alias="Shut Down Cost",
            description="Cost to shut down the generator. Only used if `committable=True`.",
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
            description="Number of snapshots that the generator was online before `n.snapshots` start. Only used if `committable=True` and `min_up_time>0`. Does not consider snapshot weightings.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1)
    
    down_time_before: Annotated[
        PropertyType,
        Field(
            alias="Down Time Before",
            description="Number of snapshots that the generator was offline before `n.snapshots` start. Only used if `committable=True` and `min_down_time>0`. Does not consider snapshot weightings.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0)
    
    ramp_limit_start_up: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Start Up",
            description="Maximum active power increase at start up, per unit of the nominal power. Only used if `committable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    ramp_limit_shut_down: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Shut Down",
            description="Maximum active power decrease at shut down, per unit of the nominal power. Only used if `committable=True`.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    weight: Annotated[
        PropertyType,
        Field(
            alias="Weight",
            description="Weighting of a generator. Only used for network clustering.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    # Time-varying attributes (can be static float or time series pd.Series)
    p_min_pu: Annotated[
        PropertyType,
        Field(
            alias="Minimum Power Per Unit",
            description="The minimum output for each snapshot per unit of `p_nom` for the optimization (e.g. a minimal dispatch level for conventional power plants). Note that if `committable=False` and `p_min_pu>0`, this represents a must-run condition.",
            ge=0,
            le=1,
        ),
    ] = PypsaProperty.create(value=0.0)
    
    p_max_pu: Annotated[
        PropertyType,
        Field(
            alias="Maximum Power Per Unit",
            description="The maximum output for each snapshot per unit of `p_nom` for the optimization (e.g. changing availability of renewable generators due to weather conditions or a de-rating of conventional power plants).",
            ge=0,
            le=1,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    p_set: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Power Set Point",
            description="Active power set point (for optimisation and power flow)",
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    q_set: Annotated[
        PropertyType,
        Field(
            alias="Reactive Power Set Point",
            description="Reactive power set point (for power flow)",
        ),
    ] = PypsaProperty.create(value=0.0, units="MVar")
    
    marginal_cost: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(
            alias="Marginal Cost",
            description="Marginal cost of production of 1 MWh.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    marginal_cost_quadratic: Annotated[
        PropertyType,
        Units("usd/MWh^2"),
        Field(
            alias="Marginal Cost Quadratic",
            description="Quadratic marginal cost of production of 1 MWh.",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh^2")
    
    efficiency: Annotated[
        PropertyType,
        Field(
            alias="Efficiency",
            description="Ratio output and primary energy carrier input (e.g. 0.4 MWh~elec~/MWh~fuel~). This is required for global constraints on primary energy in optimization.",
            ge=0,
            le=1,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    stand_by_cost: Annotated[
        PropertyType,
        Units("usd/h"),
        Field(
            alias="Stand By Cost",
            description="Stand-by cost for running the generator. This cost is incurred whenever the status is 1 (including when the dispatch decision is zero).",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="usd/h")
    
    ramp_limit_up: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Up",
            description="Maximum active power increase from one snapshot to the next, per unit of the nominal power. Ignored if NaN. Does not consider snapshot weightings.",
        ),
    ] = PypsaProperty.create(value=float('nan'))
    
    ramp_limit_down: Annotated[
        PropertyType,
        Field(
            alias="Ramp Limit Down",
            description="Maximum active power decrease from one snapshot to the next, per unit of the nominal power. Ignored if NaN. Does not consider snapshot weightings.",
        ),
    ] = PypsaProperty.create(value=float('nan'))

    @classmethod
    def example(cls) -> "PypsaGenerator":
        """Create an example generator"""
        return PypsaGenerator(
            name="ExampleGenerator",
            bus="Bus1",
            p_nom=PypsaProperty.create(value=100, units="MW"),
            marginal_cost=PypsaProperty.create(value=50, units="usd/MWh"),
            efficiency=PypsaProperty.create(value=0.9),
            control=PypsaProperty.create(value="PQ"),
        )
    