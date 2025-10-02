"""PyPSA Bus model for r2x-pypsa."""

from infrasys.component import Component
from typing import Union, Optional
import pandas as pd


class PypsaBus(Component):
    """PyPSA Bus component with all standard PyPSA attributes."""

    # Required attributes
    name: str
    
    # Static attributes with defaults (Input)
    v_nom: float = 1.0  # Nominal voltage in kV
    type: Optional[str] = None  # Placeholder for bus type. Not implemented.
    x: float = 0.0  # Longitude; the Spatial Reference System Identifier (SRID) is set in n.srid.
    y: float = 0.0  # Latitude; the Spatial Reference System Identifier (SRID) is set in n.srid.
    carrier: str = "AC"  # Carrier, such as "AC", "DC", "heat" or "gas".
    unit: Optional[str] = None  # Unit of the bus' carrier if the implicitly assumed unit ("MW") is inappropriate (e.g. "t/h"). Only descriptive. Does not influence any PyPSA functions.
    location: Optional[str] = None  # Location of the bus. Does not influence the optimisation model but can be used for aggregation with n.statistics.
    v_mag_pu_min: float = 0.0  # Minimum desired voltage, per unit of v_nom. Placeholder attribute not currently used by any functions.
    v_mag_pu_max: float = float('inf')  # Maximum desired voltage, per unit of v_nom. Placeholder attribute not currently used by any functions.
    
    # Time-varying attributes (can be static float or time series pd.Series)
    # Note: These override the static versions when time series data exists
    v_mag_pu_set: Union[float, pd.Series] = 1.0  # Voltage magnitude set point, per unit of v_nom.
