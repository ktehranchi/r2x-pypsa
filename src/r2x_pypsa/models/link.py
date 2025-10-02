"""PyPSA Link model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union, Optional
import pandas as pd


class PypsaLink(Component):
    """PyPSA Link component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus0: str
    bus1: str
    
    # Static attributes with defaults (Input)
    type: Optional[str] = None
    carrier: Optional[str] = None
    active: bool = True
    build_year: int = 0
    lifetime: float = float('inf')
    p_nom: float = 0.0
    p_nom_mod: float = 0.0
    p_nom_extendable: bool = False
    p_nom_min: float = 0.0
    p_nom_max: float = float('inf')
    capital_cost: float = 0.0
    length: float = 0.0
    terrain_factor: float = 1.0
    committable: bool = False
    start_up_cost: float = 0.0
    shut_down_cost: float = 0.0
    min_up_time: int = 0
    min_down_time: int = 0
    up_time_before: int = 1
    down_time_before: int = 0
    ramp_limit_start_up: float = 1.0
    ramp_limit_shut_down: float = 1.0
    p_nom_opt: float = 0.0  # Output attribute
    
    # Time-varying attributes (can be static float or time series pd.Series)
    efficiency: Union[float, pd.Series] = 1.0
    p_set: Union[float, pd.Series] = float('nan')
    p_min_pu: Union[float, pd.Series] = 0.0
    p_max_pu: Union[float, pd.Series] = 1.0
    marginal_cost: Union[float, pd.Series] = 0.0
    marginal_cost_quadratic: Union[float, pd.Series] = 0.0
    stand_by_cost: Union[float, pd.Series] = 0.0
    ramp_limit_up: Union[float, pd.Series] = float('nan')
    ramp_limit_down: Union[float, pd.Series] = float('nan')
