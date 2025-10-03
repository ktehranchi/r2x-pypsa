"""Unit validation system for PyPSA components."""

from typing import Any

import pint
from pydantic_core import core_schema
from r2x.units import ureg

from r2x_pypsa.models.property_values import PypsaProperty


class Units:
    """Unit compatibility validator for PyPSA components."""

    def __init__(self, expected_unit: str):
        """Create a validator for unit compatibility.

        Parameters
        ----------
        expected_unit : str
            The expected unit for validation (e.g., "MW", "usd/MWh")

        Raises
        ------
        ValueError
            If the expected unit is not a valid unit
        """
        self.expected_unit = expected_unit
        try:
            ureg.Unit(expected_unit)
        except pint.errors.UndefinedUnitError:
            raise ValueError(f"Invalid expected unit: {expected_unit}")

    def __get_pydantic_core_schema__(
        self, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        """Generate core schema for Pydantic v2.

        This method is called by Pydantic during model validation.

        Parameters
        ----------
        source_type : Any
            The source type to validate
        handler : Any
            The Pydantic schema handler

        Returns
        -------
        core_schema.CoreSchema
            The core schema for validation
        """
        schema = handler(source_type)
        return core_schema.with_info_after_validator_function(
            self.validate,
            schema,
            metadata={"units": self.expected_unit},
        )

    def validate(
        self, input_value: Any, info: core_schema.ValidationInfo | None
    ) -> Any:
        """Validate units are compatible with Pydantic v2 approach.

        Parameters
        ----------
        input_value : Any
            The value to validate
        info : core_schema.ValidationInfo | None
            Validation info

        Returns
        -------
        Any
            The validated value

        Raises
        ------
        ValueError
            If units are not compatible
        """
        # Skip validation if it's not a property or doesn't have units
        if not isinstance(input_value, PypsaProperty) or not input_value.units:
            return input_value

        try:
            # Check dimensional compatibility
            ureg.Quantity(1, input_value.units).to(self.expected_unit)
            return input_value
        except pint.errors.DimensionalityError:
            raise ValueError(
                f"Units '{input_value.units}' are not compatible with '{self.expected_unit}'"
            )
        except Exception as e:
            raise ValueError(f"Unit validation error: {e}")
