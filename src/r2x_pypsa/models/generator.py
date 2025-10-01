"""PyPSA Generator model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union, Optional
import pandas as pd


class PypsaGenerator(Component):
    """PyPSA Generator component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus: str
    
    # Static attributes with defaults (Input)
    control: str = "PQ"
    type: Optional[str] = None
    p_nom: float = 0.0
    p_nom_mod: float = 0.0
    p_nom_extendable: bool = False
    p_nom_min: float = 0.0
    p_nom_max: float = float('inf')
    e_sum_min: float = float('-inf')
    e_sum_max: float = float('inf')
    sign: float = 1.0
    carrier: Optional[str] = None
    active: bool = True
    build_year: int = 0
    lifetime: float = float('inf')
    capital_cost: float = 0.0
    
    # Unit commitment attributes
    committable: bool = False
    start_up_cost: float = 0.0
    shut_down_cost: float = 0.0
    stand_by_cost: float = 0.0
    min_up_time: int = 0
    min_down_time: int = 0
    up_time_before: int = 1
    down_time_before: int = 0
    ramp_limit_up: float = float('nan')
    ramp_limit_down: float = float('nan')
    ramp_limit_start_up: float = 1.0
    ramp_limit_shut_down: float = 1.0
    weight: float = 1.0
    p_nom_opt: float = 0.0
    
    # Time-varying attributes (can be static float or time series pd.Series)
    # Note: These override the static versions when time series data exists
    p_min_pu: Union[float, pd.Series] = 0.0
    p_max_pu: Union[float, pd.Series] = 1.0
    p_set: Union[float, pd.Series] = 0.0
    q_set: Union[float, pd.Series] = 0.0
    marginal_cost: Union[float, pd.Series] = 0.0
    marginal_cost_quadratic: Union[float, pd.Series] = 0.0
    efficiency: Union[float, pd.Series] = 1.0
    stand_by_cost: Union[float, pd.Series] = 0.0
    ramp_limit_up: Union[float, pd.Series] = float('nan')
    ramp_limit_down: Union[float, pd.Series] = float('nan')
    
    # Series-only attributes (always time series, never static)
    p: pd.Series = pd.Series(dtype=float)  # Active power at bus (series)
    q: pd.Series = pd.Series(dtype=float)  # Reactive power (series)
    status: pd.Series = pd.Series(dtype=float)  # Status in snapshot (series, only if committable=True)
    start_up: pd.Series = pd.Series(dtype=float)  # Whether unit was started (series, only if committable=True)
    shut_down: pd.Series = pd.Series(dtype=float)  # Whether unit was shut down (series, only if committable=True)
    mu_upper: pd.Series = pd.Series(dtype=float)  # Shadow price of upper p_nom limit (series)
    mu_lower: pd.Series = pd.Series(dtype=float)  # Shadow price of lower p_nom limit (series)
    mu_p_set: pd.Series = pd.Series(dtype=float)  # Shadow price of fixed dispatch p_set (series)
    mu_ramp_limit_up: pd.Series = pd.Series(dtype=float)  # Shadow price of upper ramp up limit (series)
    mu_ramp_limit_down: pd.Series = pd.Series(dtype=float)  # Shadow price of lower ramp down limit (series)