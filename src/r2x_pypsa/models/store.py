"""PyPSA Store model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union, Optional
import pandas as pd


class PypsaStore(Component):
    """PyPSA Store component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus: str
    
    # Static attributes with defaults (Input)
    type: Optional[str] = None
    carrier: Optional[str] = None
    e_nom: float = 0.0
    e_nom_mod: float = 0.0
    e_nom_extendable: bool = False
    e_nom_min: float = 0.0
    e_nom_max: float = float('inf')
    e_initial: float = 0.0
    e_initial_per_period: bool = False
    e_cyclic: bool = False
    e_cyclic_per_period: bool = True
    sign: float = 1.0
    capital_cost: float = 0.0
    active: bool = True
    build_year: int = 0
    lifetime: float = float('inf')
    e_nom_opt: float = 0.0  # Output attribute
    
    # Time-varying attributes (can be static float or time series pd.Series)
    e_min_pu: Union[float, pd.Series] = 0.0
    e_max_pu: Union[float, pd.Series] = 1.0
    p_set: Union[float, pd.Series] = float('nan')
    q_set: Union[float, pd.Series] = 0.0
    e_set: Union[float, pd.Series] = float('nan')
    marginal_cost: Union[float, pd.Series] = 0.0
    marginal_cost_quadratic: Union[float, pd.Series] = 0.0
    marginal_cost_storage: Union[float, pd.Series] = 0.0
    standing_loss: Union[float, pd.Series] = 0.0
