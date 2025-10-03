"""Property value classes for PyPSA components."""

from typing import Any, Callable, List, Optional, TypeVar
import pandas as pd

from pydantic import BaseModel

T = TypeVar("T")


class PypsaProperty(BaseModel):
    """Unified property class for PyPSA components.

    This class handles all types of properties: direct values,
    time series data, and metadata. A property can have any combination of these
    features simultaneously.
    """
    
    model_config = {"arbitrary_types_allowed": True}

    # Basic metadata
    units: Optional[str] = None

    # Direct value (for simple properties)
    value: Any = None

    # Time series data
    time_series: Optional[pd.Series] = None


    # Metadata for validation and constraints
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None

    def __lt__(self, other: Any) -> bool:
        """Less than comparison."""
        return self._compare(other, lambda x, y: x < y)

    def __le__(self, other: Any) -> bool:
        """Less than or equal comparison."""
        return self._compare(other, lambda x, y: x <= y)

    def __gt__(self, other: Any) -> bool:
        """Greater than comparison."""
        return self._compare(other, lambda x, y: x > y)

    def __ge__(self, other: Any) -> bool:
        """Greater than or equal comparison."""
        return self._compare(other, lambda x, y: x >= y)

    def __eq__(self, other: Any) -> bool:
        """Equal comparison."""
        return self._compare(other, lambda x, y: x == y)

    def _compare(self, other: Any, op: Callable[[Any, Any], bool]) -> bool:
        """Compare this property with another value."""
        # Get values for comparison
        values = []
        
        if self.value is not None:
            values.append(self.value)
        
        if self.time_series is not None and not self.time_series.empty:
            values.extend(self.time_series.dropna().tolist())

        if not values:
            return True  # Skip validation if no values

        # For validation constraints, all values must satisfy
        return all(v is not None and op(v, other) for v in values)

    def get_value(self) -> Any:
        """Get the default property value."""
        # Direct value for simple case
        if self.value is not None:
            return self.value

        # If we have time series, return the mean or first value
        if self.time_series is not None and not self.time_series.empty:
            return self.time_series.mean()

        return None

    def get_time_series(self) -> Optional[pd.Series]:
        """Get the time series data if available."""
        return self.time_series

    def has_time_series(self) -> bool:
        """Check if this property has time series data."""
        return self.time_series is not None and not self.time_series.empty

    def has_datafile(self) -> bool:
        """Check if this property references a datafile."""
        return bool(self.datafile_name or self.datafile_id)

    def add_time_series(self, series: pd.Series, units: Optional[str] = None) -> None:
        """Add time series data to this property."""
        self.time_series = series
        if not self.units and units:
            self.units = units

    def set_constraints(
        self,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        allowed_values: Optional[List[Any]] = None,
    ) -> None:
        """Set validation constraints for this property."""
        if min_value is not None:
            self.min_value = min_value
        if max_value is not None:
            self.max_value = max_value
        if allowed_values is not None:
            self.allowed_values = allowed_values

    def validate_constraints(self) -> bool:
        """Validate that the property values satisfy all constraints."""
        values = []
        
        if self.value is not None:
            values.append(self.value)
        
        if self.time_series is not None and not self.time_series.empty:
            values.extend(self.time_series.dropna().tolist())

        if not values:
            return True

        for value in values:
            if value is None:
                continue
                
            # Check min/max constraints
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
                
            # Check allowed values
            if self.allowed_values is not None and value not in self.allowed_values:
                return False

        return True

    @classmethod
    def create(
        cls, 
        value: Any, 
        units: Optional[str] = None,
        time_series: Optional[pd.Series] = None,
        **kwargs
    ) -> "PypsaProperty":
        """Create a property with a direct value.

        Parameters
        ----------
        value : Any
            The direct value for this property
        units : Optional[str]
            Units for this value, if applicable
        time_series : Optional[pd.Series]
            Time series data for this property
        **kwargs
            Additional keyword arguments for constraints

        Returns
        -------
        PypsaProperty
            A new property with the specified value
        """
        prop = cls(
            value=value,
            units=units,
            time_series=time_series,
            **kwargs
        )
        return prop

    @classmethod
    def create_with_time_series(
        cls,
        series: pd.Series,
        units: Optional[str] = None,
        **kwargs
    ) -> "PypsaProperty":
        """Create a property with time series data.

        Parameters
        ----------
        series : pd.Series
            Time series data
        units : Optional[str]
            Units for this value, if applicable
        **kwargs
            Additional keyword arguments for constraints

        Returns
        -------
        PypsaProperty
            A new property with the specified time series
        """
        return cls.create(
            value=series.mean() if not series.empty else None,
            units=units,
            time_series=series,
            **kwargs
        )


# Type alias for usage in component models
PropertyType = PypsaProperty


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, handling None/NaN cases.
    
    Parameters
    ----------
    value : Any
        The value to convert to float
    default : float
        Default value to return if conversion fails
        
    Returns
    -------
    float
        The converted float value or default
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """Safely convert a value to string, handling None cases.
    
    Parameters
    ----------
    value : Any
        The value to convert to string
    default : str
        Default value to return if conversion fails
        
    Returns
    -------
    str
        The converted string value or default
    """
    if value is None:
        return default
    try:
        return str(value)
    except (ValueError, TypeError):
        return default


def get_ts_or_static(network, table: str, column: str, name: str, ts_data: Any, static_data: Any, default: Any) -> PypsaProperty:
    """Get time series data if available, otherwise use static data.
    
    Parameters
    ----------
    network : Any
        The PyPSA network object
    table : str
        The table name (e.g., 'generators_t')
    column : str
        The column name (e.g., 'p_min_pu')
    name : str
        The component name
    ts_data : Any
        Time series data if available
    static_data : Any
        Static data from component attributes
    default : Any
        Default value if neither time series nor static data available
        
    Returns
    -------
    PypsaProperty
        A property with time series data if available, otherwise static data
    """
    # If time series data is available and not empty
    if ts_data is not None and not ts_data.empty and name in ts_data.columns:
        return PypsaProperty.create_with_time_series(ts_data[name], units=None)
    
    # Otherwise use static data or default
    value = static_data if static_data is not None else default
    return PypsaProperty.create(value=value)


def get_series_only(network: Any, name: str, column: str, default: Any) -> pd.Series:
    """Get time series data only.

    Parameters
    ----------
    network : Any
        The PyPSA network object
    name : str
        The name of the component
    column : str
        The column name (e.g., 'p', 'q')
    default : Any
        Default value if no data is found

    Returns
    -------
    pd.Series
        A pandas Series containing time series data.
    """
    # Access the time-varying attribute table directly
    # For example, network.generators_t.p, network.buses_t.p
    # Try to determine component type from the network
    if name in network.generators.index:
        time_varying_table = network.generators_t
    elif name in network.buses.index:
        time_varying_table = network.buses_t
    elif name in network.storage_units.index:
        time_varying_table = network.storage_units_t
    elif name in network.links.index:
        time_varying_table = network.links_t
    elif name in network.lines.index:
        time_varying_table = network.lines_t
    elif name in network.loads.index:
        time_varying_table = network.loads_t
    elif name in network.stores.index:
        time_varying_table = network.stores_t
    else:
        # If no time series data, return a series of default values
        return pd.Series(default, index=network.snapshots)

    if column in time_varying_table and name in time_varying_table[column]:
        return time_varying_table[column][name]
    else:
        # If no time series data, return a series of default values
        return pd.Series(default, index=network.snapshots)