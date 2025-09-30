"""Utility helpers for PyPSA property resolution."""

from __future__ import annotations

from typing import Any

import pandas as pd


def get_ts_or_static(
    network: Any,
    ts_object_name: str,
    attr: str,
    component_name: str,
    dense_df: pd.DataFrame,
    static_row: pd.Series,
    default: float,
):
    """Return time series for attr if the time series object is populated and contains the component; else static scalar.

    Parameters
    ----------
    network : pypsa.Network
        The PyPSA network object
    ts_object_name : str
        Name of the time series object, e.g. "generators_t"
    attr : str
        Attribute name, e.g. "marginal_cost"
    component_name : str
        Name of the component, e.g. generator name
    dense_df : pd.DataFrame
        DataFrame from network.get_switchable_as_dense(component, attr)
    static_row : pd.Series
        Row from the static component table (e.g., n.generators.loc[name])
    default : float
        Fallback scalar if static_row[attr] is NaN/missing

    Returns
    -------
    Union[float, pd.Series]
        Time series if available, otherwise static scalar value
    """
    # Get the time series object (e.g., network.generators_t)
    ts_object = getattr(network, ts_object_name, None)
    ts_df = getattr(ts_object, attr, None) if ts_object else None
    
    # Use time series if it exists and has the component
    if ts_df is not None and not ts_df.empty and component_name in ts_df.columns:
        return dense_df[component_name]

    # Fall back to static value
    return static_row.get(attr, default)


