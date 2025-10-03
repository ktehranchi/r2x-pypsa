# Pydantic Field Specifications for r2x-pypsa

This document explains the Pydantic field specifications used in the r2x-pypsa library, inspired by the patterns from r2x-plexos.

## Overview

The r2x-pypsa library uses a sophisticated Pydantic-based field specification system that provides:

- **Type Safety**: Strong typing with Pydantic validation
- **Unit Validation**: Automatic unit compatibility checking
- **Rich Metadata**: Comprehensive field descriptions and constraints
- **Flexible Properties**: Support for both static values and time series data
- **Validation**: Built-in constraint validation (min/max values, enums, etc.)

## Key Components

### 1. PypsaProperty Class

The `PypsaProperty` class is the core property system that handles:

```python
from r2x_pypsa.models.property_values import PypsaProperty

# Create a simple property
prop = PypsaProperty.create(value=100, units="MW")

# Create a property with time series
import pandas as pd
ts = pd.Series([1, 2, 3], index=pd.date_range('2023-01-01', periods=3))
prop_ts = PypsaProperty.create_with_time_series(ts, units="MW")

# Create a property with constraints
prop_constrained = PypsaProperty.create(
    value=50, 
    units="MW",
    min_value=0,
    max_value=100
)
```

### 2. Units Validation System

The `Units` class provides automatic unit validation:

```python
from r2x_pypsa.models.units import Units

# This will validate that the property has compatible units
Units("MW")  # Validates against MW units
Units("usd/MWh")  # Validates against cost per energy units
```

### 3. Field Specification Pattern

The main pattern for defining fields combines:

- `Annotated` type hints
- `Units` validation
- `Field` metadata
- `PypsaProperty` as the value type

```python
from typing import Annotated
from pydantic import Field
from r2x_pypsa.models.property_values import PypsaProperty, PropertyType
from r2x_pypsa.models.units import Units

# Basic field pattern
field_name: Annotated[
    PropertyType,  # The actual type (PypsaProperty)
    Units("MW"),   # Unit validation
    Field(         # Pydantic field metadata
        alias="Field Name",
        description="Field description",
        ge=0,       # Validation constraints
        le=100,
    ),
] = PypsaProperty.create(value=0, units="MW")
```

## Field Specification Examples

### Simple Value Field

```python
control: Annotated[
    PropertyType,
    Field(
        alias="Control",
        description="Control type for the generator",
        json_schema_extra={"enum": ["PQ", "PV", "Slack"]},
    ),
] = PypsaProperty.create(value="PQ")
```

### Numeric Field with Units and Constraints

```python
p_nom: Annotated[
    PropertyType,
    Units("MW"),
    Field(
        alias="Nominal Power",
        description="Nominal power capacity",
        ge=0,  # Greater than or equal to 0
    ),
] = PypsaProperty.create(value=0.0, units="MW")
```

### Boolean Field

```python
active: Annotated[
    PropertyType,
    Field(
        alias="Active",
        description="Whether the generator is active",
    ),
] = PypsaProperty.create(value=True)
```

### Field with Range Constraints

```python
efficiency: Annotated[
    PropertyType,
    Field(
        alias="Efficiency",
        description="Generator efficiency",
        ge=0,  # Greater than or equal to 0
        le=1,  # Less than or equal to 1
    ),
] = PypsaProperty.create(value=1.0)
```

## Advanced Features

### Time Series Support

Properties can contain both static values and time series data:

```python
# Static value
marginal_cost = PypsaProperty.create(value=50, units="usd/MWh")

# Time series
import pandas as pd
ts = pd.Series([45, 50, 55], index=pd.date_range('2023-01-01', periods=3))
marginal_cost_ts = PypsaProperty.create_with_time_series(ts, units="usd/MWh")

# Mixed (both static and time series)
marginal_cost_mixed = PypsaProperty.create(value=50, units="usd/MWh")
marginal_cost_mixed.add_time_series(ts)
```

### Constraint Validation

Properties can have built-in validation constraints:

```python
prop = PypsaProperty.create(value=75, units="MW")
prop.set_constraints(min_value=0, max_value=100, allowed_values=[25, 50, 75, 100])

# Validate constraints
is_valid = prop.validate_constraints()  # True
```

### Unit Compatibility

The units system ensures dimensional consistency:

```python
# This will work
power_prop = PypsaProperty.create(value=100, units="MW")
Units("MW").validate(power_prop)  # Valid

# This will raise an error
cost_prop = PypsaProperty.create(value=50, units="usd/MWh")
Units("MW").validate(cost_prop)  # ValueError: Units incompatible
```

## Usage in Component Classes

Here's how to use these patterns in your own component classes:

```python
from infrasys.component import Component
from typing import Annotated
from pydantic import Field
from r2x_pypsa.models.property_values import PypsaProperty, PropertyType
from r2x_pypsa.models.units import Units

class MyComponent(Component):
    """Example component with Pydantic field specifications."""
    
    # Required attributes
    name: str
    
    # Field with units and constraints
    capacity: Annotated[
        PropertyType,
        Units("MW"),
        Field(
            alias="Capacity",
            description="Component capacity",
            ge=0,
        ),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    # Field with enum constraints
    status: Annotated[
        PropertyType,
        Field(
            alias="Status",
            description="Component status",
            json_schema_extra={"enum": ["active", "inactive", "maintenance"]},
        ),
    ] = PypsaProperty.create(value="active")
    
    # Field with range constraints
    efficiency: Annotated[
        PropertyType,
        Field(
            alias="Efficiency",
            description="Component efficiency",
            ge=0,
            le=1,
        ),
    ] = PypsaProperty.create(value=1.0)
    
    @classmethod
    def example(cls) -> "MyComponent":
        """Create an example component."""
        return MyComponent(
            name="ExampleComponent",
            capacity=PypsaProperty.create(value=100, units="MW"),
            efficiency=PypsaProperty.create(value=0.9),
        )
```

## Benefits

This Pydantic-based approach provides several key benefits:

1. **Type Safety**: Compile-time type checking and runtime validation
2. **Unit Safety**: Automatic unit compatibility checking prevents dimensional errors
3. **Rich Metadata**: Comprehensive field descriptions and constraints
4. **Flexibility**: Support for both static values and time series data
5. **Validation**: Built-in constraint validation with clear error messages
6. **Documentation**: Self-documenting code with field descriptions and constraints
7. **IDE Support**: Better autocomplete and type hints in IDEs
8. **Serialization**: Automatic JSON schema generation and serialization support

## Migration from Simple Attributes

If you're migrating from simple attribute definitions, here's the transformation:

**Before:**
```python
class OldGenerator(Component):
    p_nom: float = 0.0
    marginal_cost: float = 0.0
    active: bool = True
```

**After:**
```python
class NewGenerator(Component):
    p_nom: Annotated[
        PropertyType,
        Units("MW"),
        Field(alias="Nominal Power", description="Nominal power capacity", ge=0),
    ] = PypsaProperty.create(value=0.0, units="MW")
    
    marginal_cost: Annotated[
        PropertyType,
        Units("usd/MWh"),
        Field(alias="Marginal Cost", description="Marginal cost of generation", ge=0),
    ] = PypsaProperty.create(value=0.0, units="usd/MWh")
    
    active: Annotated[
        PropertyType,
        Field(alias="Active", description="Whether the generator is active"),
    ] = PypsaProperty.create(value=True)
```

This transformation provides all the benefits mentioned above while maintaining the same basic functionality.
