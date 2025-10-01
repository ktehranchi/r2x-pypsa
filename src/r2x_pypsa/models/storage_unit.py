"""PyPSA Storage Unit model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union, Optional
import pandas as pd


class PypsaStorageUnit(Component):
    """PyPSA Storage Unit component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus: str
    
    # Static attributes with defaults (Input)
    control: str = "PQ"  # P,Q,V control strategy for PF, must be "PQ", "PV" or "Slack"
    type: Optional[str] = None  # Placeholder for storage unit type. Not yet implemented.
    p_nom: float = 0.0  # Nominal power for limits on p in optimisation
    p_nom_mod: float = 0.0  # Nominal power of the storage unit module
    p_nom_extendable: bool = False  # Switch to allow capacity p_nom to be extended
    p_nom_min: float = 0.0  # If p_nom_extendable=True, set the minimum value of p_nom_opt
    p_nom_max: float = float('inf')  # If p_nom_extendable=True, set the maximum value of p_nom_opt
    sign: float = 1.0  # Sign denoting the orientation of the dispatch variable
    carrier: Optional[str] = None  # Prime mover energy carrier
    capital_cost: float = 0.0  # Fixed period costs of extending p_nom by 1 MW
    active: bool = True  # Whether to consider the component in optimisation
    build_year: int = 0  # Build year
    lifetime: float = float('inf')  # Lifetime
    state_of_charge_initial: float = 0.0  # State of charge before the snapshots
    state_of_charge_initial_per_period: bool = False  # Switch for initial SOC per period
    cyclic_state_of_charge: bool = False  # Switch for cyclic SOC constraints
    cyclic_state_of_charge_per_period: bool = True  # Switch for cyclic constraints per period
    max_hours: float = 1.0  # Maximum state of charge capacity in terms of hours
    
    # Time-varying attributes (can be static float or time series pd.Series)
    # Note: These override the static versions when time series data exists
    p_min_pu: Union[float, pd.Series] = -1.0  # Minimum output per unit of p_nom
    p_max_pu: Union[float, pd.Series] = 1.0  # Maximum output per unit of p_nom
    p_set: Union[float, pd.Series] = float('nan')  # Active power set point
    q_set: Union[float, pd.Series] = 0.0  # Reactive power set point
    p_dispatch_set: Union[float, pd.Series] = float('nan')  # Active power dispatch set point
    p_store_set: Union[float, pd.Series] = float('nan')  # Active power charging set point
    spill_cost: Union[float, pd.Series] = 0.0  # Cost of spilling 1 MWh
    marginal_cost: Union[float, pd.Series] = 0.0  # Marginal cost of production (discharge)
    marginal_cost_quadratic: Union[float, pd.Series] = 0.0  # Quadratic marginal cost
    marginal_cost_storage: Union[float, pd.Series] = 0.0  # Marginal cost of energy storage
    state_of_charge_set: Union[float, pd.Series] = float('nan')  # State of charge set points
    efficiency_store: Union[float, pd.Series] = 1.0  # Efficiency of storage on the way in
    efficiency_dispatch: Union[float, pd.Series] = 1.0  # Efficiency of storage on the way out
    standing_loss: Union[float, pd.Series] = 0.0  # Losses per hour to state of charge
    inflow: Union[float, pd.Series] = 0.0  # Inflow to the state of charge
    
    # Output attributes (set by PyPSA functions)
    p_nom_opt: float = 0.0  # Optimised nominal power
