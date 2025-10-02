"""PyPSA Line model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union, Optional
import pandas as pd


class PypsaLine(Component):
    """PyPSA Line component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus0: str
    bus1: str
    
    # Static attributes with defaults (Input)
    type: Optional[str] = None
    x: float = 0.0
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    s_nom: float = 0.0
    s_nom_mod: float = 0.0
    s_nom_extendable: bool = False
    s_nom_min: float = 0.0
    s_nom_max: float = float('inf')
    capital_cost: float = 0.0
    active: bool = True
    build_year: int = 0
    lifetime: float = float('inf')
    length: float = 0.0
    carrier: str = "AC"
    terrain_factor: float = 1.0
    num_parallel: float = 1.0
    v_ang_min: float = float('-inf')
    v_ang_max: float = float('inf')
    
    # Time-varying attributes (can be static float or time series pd.Series)
    s_max_pu: Union[float, pd.Series] = 1.0
