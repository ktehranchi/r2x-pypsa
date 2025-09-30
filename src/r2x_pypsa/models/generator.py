"""PyPSA Generator model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union
import pandas as pd


class PypsaGenerator(Component):
    """PyPSA Generator component."""

    name: str
    bus: str
    carrier: str
    p_nom: float = 0.0
    p_nom_extendable: bool = False
    capital_cost: float = 0.0
    
    # Time-varying fields can be static (float) or time series (pd.Series)
    marginal_cost: Union[float, pd.Series] = 0.0
    efficiency: Union[float, pd.Series] = 1.0
    p_max_pu: Union[float, pd.Series] = 1.0
    p_min_pu: Union[float, pd.Series] = 0.0
