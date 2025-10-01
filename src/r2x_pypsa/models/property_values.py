"""Utility helpers for PyPSA property resolution."""

from __future__ import annotations

from typing import Any, Union, Optional

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


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, handling NaN and None values.
    
    Parameters
    ----------
    value : Any
        Value to convert to float
    default : float, default=0.0
        Default value to return if conversion fails or value is NaN/None
        
    Returns
    -------
    float
        Converted float value or default
    """
    return float(value) if not pd.isna(value) else default


def safe_str(value: Any) -> Optional[str]:
    """Safely convert a value to string, handling NaN and None values.
    
    Parameters
    ----------
    value : Any
        Value to convert to string
        
    Returns
    -------
    Optional[str]
        Converted string value or None if value is NaN/None
    """
    return str(value) if not pd.isna(value) else None


def get_series_only(
    network: Any,
    component_name: str,
    attr: str,
    default: float = 0.0,
) -> pd.Series:
    """Return time series for series-only attributes from time series component object.
    
    For attributes that are always time series (never static), this function
    extracts the time series data from the time series component object (e.g., n.generators_t.p)
    or creates a default series if not available.
    
    Parameters
    ----------
    network : pypsa.Network
        The PyPSA network object
    component_name : str
        Name of the component, e.g. generator name
    attr : str
        Attribute name, e.g. "p"
    default : float, default=0.0
        Default value for the series if component not found
        
    Returns
    -------
    pd.Series
        Time series data for the component
    """
    # Get the time series component object (e.g., network.generators_t)
    ts_component_obj = getattr(network, 'generators_t', None)
    if ts_component_obj is None:
        return pd.Series(default, index=network.snapshots)
    
    # Get the attribute DataFrame (e.g., network.generators_t.p)
    attr_df = getattr(ts_component_obj, attr, None)
    if attr_df is None or attr_df.empty:
        return pd.Series(default, index=network.snapshots)
    
    # Check if component exists in the attribute DataFrame
    if component_name in attr_df.columns:
        return attr_df[component_name]
    
    # Create default series with network snapshots
    return pd.Series(default, index=network.snapshots)


