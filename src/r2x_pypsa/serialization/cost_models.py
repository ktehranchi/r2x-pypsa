"""Cost model creation utilities for PyPSA to PSY serialization."""

from typing import Any
from loguru import logger
from r2x.api import System
from r2x.models.costs import OperationalCost
from r2x.models import ThermalStandard, HydroDispatch, RenewableDispatch, EnergyReservoirStorage

from infrasys.component import Component as PypsaDevice
from r2x_pypsa.serialization.utils import get_pypsa_property


def create_operational_cost(
    psy_component: Any,
    pypsa_component: PypsaDevice,
    system: System,
) -> OperationalCost | None:
    """Create operational cost model for PSY component from PyPSA data.

    Parameters
    ----------
    psy_component : Any
        The PSY component to create costs for
    pypsa_component : PypsaDevice
        The PyPSA component with cost data
    system : System
        The system containing the component

    Returns
    -------
    OperationalCost | None
        The operational cost model or None if no cost data available
    """
    try:
        # Extract common cost data from PyPSA component
        marginal_cost = get_pypsa_property(system, pypsa_component, "marginal_cost")
        marginal_cost_quadratic = get_pypsa_property(system, pypsa_component, "marginal_cost_quadratic")

        # Handle different cost structures based on component type
        if isinstance(psy_component, ThermalStandard):
            # Only extract thermal-specific costs for thermal components
            start_up_cost = get_pypsa_property(system, pypsa_component, "start_up_cost")
            shut_down_cost = get_pypsa_property(system, pypsa_component, "shut_down_cost")
            stand_by_cost = get_pypsa_property(system, pypsa_component, "stand_by_cost")
            return _create_thermal_operational_cost(
                marginal_cost, marginal_cost_quadratic, start_up_cost, 
                shut_down_cost, stand_by_cost
            )
        elif isinstance(psy_component, (HydroDispatch, RenewableDispatch)):
            return _create_renewable_operational_cost(marginal_cost, marginal_cost_quadratic)
        elif isinstance(psy_component, EnergyReservoirStorage):
            return _create_storage_operational_cost(
                marginal_cost, marginal_cost_quadratic, 
                get_pypsa_property(system, pypsa_component, "marginal_cost_storage")
            )
        else:
            # Generic operational cost
            return _create_generic_operational_cost(marginal_cost, marginal_cost_quadratic)

    except Exception as e:
        logger.warning(f"Error creating operational cost for {pypsa_component.name}: {e}")
        return None


def _create_thermal_operational_cost(
    marginal_cost: float | None,
    marginal_cost_quadratic: float | None,
    start_up_cost: float | None,
    shut_down_cost: float | None,
    stand_by_cost: float | None,
) -> OperationalCost | None:
    """Create operational cost for thermal generators."""
    if marginal_cost is None and marginal_cost_quadratic is None:
        return None

    # Create cost model with available data
    cost_data = {}
    
    if marginal_cost is not None and marginal_cost > 0:
        cost_data["variable"] = marginal_cost
    
    if marginal_cost_quadratic is not None and marginal_cost_quadratic > 0:
        cost_data["quadratic"] = marginal_cost_quadratic
    
    if start_up_cost is not None and start_up_cost > 0:
        cost_data["start_up"] = start_up_cost
    
    if shut_down_cost is not None and shut_down_cost > 0:
        cost_data["shut_down"] = shut_down_cost
    
    if stand_by_cost is not None and stand_by_cost > 0:
        cost_data["stand_by"] = stand_by_cost

    if not cost_data:
        return None

    return OperationalCost.model_construct(**cost_data)


def _create_renewable_operational_cost(
    marginal_cost: float | None,
    marginal_cost_quadratic: float | None,
) -> OperationalCost | None:
    """Create operational cost for renewable generators."""
    if marginal_cost is None and marginal_cost_quadratic is None:
        return None

    cost_data = {}
    
    if marginal_cost is not None and marginal_cost > 0:
        cost_data["variable"] = marginal_cost
    
    if marginal_cost_quadratic is not None and marginal_cost_quadratic > 0:
        cost_data["quadratic"] = marginal_cost_quadratic

    if not cost_data:
        return None

    return OperationalCost.model_construct(**cost_data)


def _create_storage_operational_cost(
    marginal_cost: float | None,
    marginal_cost_quadratic: float | None,
    marginal_cost_storage: float | None,
) -> OperationalCost | None:
    """Create operational cost for storage units."""
    if marginal_cost is None and marginal_cost_quadratic is None and marginal_cost_storage is None:
        return None

    cost_data = {}
    
    if marginal_cost is not None and marginal_cost > 0:
        cost_data["variable"] = marginal_cost
    
    if marginal_cost_quadratic is not None and marginal_cost_quadratic > 0:
        cost_data["quadratic"] = marginal_cost_quadratic
    
    if marginal_cost_storage is not None and marginal_cost_storage > 0:
        cost_data["storage"] = marginal_cost_storage

    if not cost_data:
        return None

    return OperationalCost.model_construct(**cost_data)


def _create_generic_operational_cost(
    marginal_cost: float | None,
    marginal_cost_quadratic: float | None,
) -> OperationalCost | None:
    """Create generic operational cost model."""
    if marginal_cost is None and marginal_cost_quadratic is None:
        return None

    cost_data = {}
    
    if marginal_cost is not None and marginal_cost > 0:
        cost_data["variable"] = marginal_cost
    
    if marginal_cost_quadratic is not None and marginal_cost_quadratic > 0:
        cost_data["quadratic"] = marginal_cost_quadratic

    if not cost_data:
        return None

    return OperationalCost.model_construct(**cost_data)
