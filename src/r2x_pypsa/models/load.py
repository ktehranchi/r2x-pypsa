"""PyPSA Load model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union, Optional
import pandas as pd


class PypsaLoad(Component):
    """PyPSA Load component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    bus: str
    
    # Static attributes with defaults (Input)
    carrier: Optional[str] = None
    type: Optional[str] = None
    sign: float = -1.0
    active: bool = True
    
    # Time-varying attributes (can be static float or time series pd.Series)
    p_set: Union[float, pd.Series] = 0.0
    q_set: Union[float, pd.Series] = 0.0
