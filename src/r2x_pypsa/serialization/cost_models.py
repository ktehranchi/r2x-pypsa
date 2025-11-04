"""Cost model creation utilities for PyPSA to PSY serialization."""

from functools import singledispatch
from typing import Any
from loguru import logger
from r2x.api import System
from r2x.models.costs import OperationalCost
from r2x.models import (
    ThermalStandard, 
    HydroDispatch, 
    RenewableDispatch, 
    EnergyReservoirStorage,
    StorageCost,
    ThermalGenerationCost,
    RenewableGenerationCost,
    HydroGenerationCost
)
from infrasys.cost_curves import CostCurve, UnitSystem
from infrasys.value_curves import LinearCurve

from infrasys.component import Component as PypsaDevice
from r2x_pypsa.serialization.utils import get_pypsa_property


@singledispatch
def create_operational_cost(
    psy_component: Any,
    pypsa_component: PypsaDevice,
    system: System,
) -> OperationalCost | StorageCost | ThermalGenerationCost | RenewableGenerationCost | HydroGenerationCost | None:
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
    OperationalCost | StorageCost | ThermalGenerationCost | RenewableGenerationCost | HydroGenerationCost | None
        The appropriate cost model for the component type or None if no cost data available
    """
    raise NotImplementedError(
        f"No cost model implementation for {type(psy_component).__name__}"
    )


@create_operational_cost.register
def _(
    psy_component: ThermalStandard,
    pypsa_component: PypsaDevice,
    system: System,
) -> ThermalGenerationCost | None:
    """Create thermal generation cost model for thermal generators.

    Parameters
    ----------
    psy_component : ThermalStandard
        The thermal generator component
    pypsa_component : PypsaDevice
        The PyPSA component with cost data
    system : System
        The system containing the component

    Returns
    -------
    ThermalGenerationCost | None
        The thermal generation cost model or None if no cost data available
    """
    try:
        # Extract cost data from PyPSA component
        marginal_cost = get_pypsa_property(system, pypsa_component, "marginal_cost")
        marginal_cost_quadratic = get_pypsa_property(system, pypsa_component, "marginal_cost_quadratic")
        start_up_cost = get_pypsa_property(system, pypsa_component, "start_up_cost")
        shut_down_cost = get_pypsa_property(system, pypsa_component, "shut_down_cost")
        
        # If no cost data available, return None
        if marginal_cost is None and marginal_cost_quadratic is None:
            return None

        # Create variable cost curve
        variable = None
        if marginal_cost is not None and marginal_cost > 0:
            variable = CostCurve(
                value_curve=LinearCurve(marginal_cost),
                power_units=UnitSystem.NATURAL_UNITS
            )
        else:
            variable = CostCurve(
                value_curve=LinearCurve(0.0),
                power_units=UnitSystem.NATURAL_UNITS
            )

        return ThermalGenerationCost(
            fixed=0.0,  # PyPSA doesn't have fixed cost concept
            shut_down=shut_down_cost or 0.0,
            start_up=start_up_cost or 0.0,
            variable=variable,
        )

    except Exception as e:
        logger.warning(f"Error creating thermal cost for {pypsa_component.name}: {e}")
        return None


@create_operational_cost.register
def _(
    psy_component: HydroDispatch,
    pypsa_component: PypsaDevice,
    system: System,
) -> HydroGenerationCost | None:
    """Create hydro generation cost model for hydro generators.

    Parameters
    ----------
    psy_component : HydroDispatch
        The hydro generator component
    pypsa_component : PypsaDevice
        The PyPSA component with cost data
    system : System
        The system containing the component

    Returns
    -------
    HydroGenerationCost | None
        The hydro generation cost model or None if no cost data available
    """
    try:
        # Extract cost data from PyPSA component
        marginal_cost = get_pypsa_property(system, pypsa_component, "marginal_cost")
        
        # If no cost data available, return None
        if marginal_cost is None:
            return None

        # Create variable cost curve
        variable = CostCurve(
            value_curve=LinearCurve(marginal_cost),
            power_units=UnitSystem.NATURAL_UNITS
        )

        return HydroGenerationCost(
            fixed=0.0,  # PyPSA doesn't have fixed cost concept for hydro
            variable=variable,
        )

    except Exception as e:
        logger.warning(f"Error creating hydro cost for {pypsa_component.name}: {e}")
        return None


@create_operational_cost.register
def _(
    psy_component: RenewableDispatch,
    pypsa_component: PypsaDevice,
    system: System,
) -> RenewableGenerationCost | None:
    """Create renewable generation cost model for renewable generators.

    Parameters
    ----------
    psy_component : RenewableDispatch
        The renewable generator component
    pypsa_component : PypsaDevice
        The PyPSA component with cost data
    system : System
        The system containing the component

    Returns
    -------
    RenewableGenerationCost | None
        The renewable generation cost model or None if no cost data available
    """
    try:
        # Extract cost data from PyPSA component
        marginal_cost = get_pypsa_property(system, pypsa_component, "marginal_cost")
        
        # Create variable cost curve (default to 0.0 if no cost specified)
        variable = CostCurve(
            value_curve=LinearCurve(marginal_cost or 0.0),
            power_units=UnitSystem.NATURAL_UNITS
        )
        
        # Create curtailment cost curve (default to 0.0)
        curtailment_cost = CostCurve(
            value_curve=LinearCurve(0.0),
            power_units=UnitSystem.NATURAL_UNITS
        )

        return RenewableGenerationCost(
            curtailment_cost=curtailment_cost,
            variable=variable,
        )

    except Exception as e:
        logger.warning(f"Error creating renewable cost for {pypsa_component.name}: {e}")
        return None


@create_operational_cost.register
def _(
    psy_component: EnergyReservoirStorage,
    pypsa_component: PypsaDevice,
    system: System,
) -> StorageCost | None:
    """Create storage cost model for energy storage systems.

    Parameters
    ----------
    psy_component : EnergyReservoirStorage
        The storage component
    pypsa_component : PypsaDevice
        The PyPSA component with cost data
    system : System
        The system containing the component

    Returns
    -------
    StorageCost | None
        The storage cost model or None if no cost data available
    """
    try:
        # Extract cost data from PyPSA component
        marginal_cost = get_pypsa_property(system, pypsa_component, "marginal_cost")
        marginal_cost_storage = get_pypsa_property(system, pypsa_component, "marginal_cost_storage")
        
        # If no cost data available, return None
        if marginal_cost is None and marginal_cost_storage is None:
            return None

        # Create charge and discharge cost curves
        # PyPSA uses marginal_cost for both charge and discharge
        charge_variable_cost = CostCurve(
            value_curve=LinearCurve(marginal_cost or 0.0),
            power_units=UnitSystem.NATURAL_UNITS
        )
        
        discharge_variable_cost = CostCurve(
            value_curve=LinearCurve(marginal_cost or 0.0),
            power_units=UnitSystem.NATURAL_UNITS
        )

        return StorageCost(
            fixed=0.0,  # PyPSA doesn't have fixed cost concept for storage
            start_up=0.0,  # PyPSA doesn't have start up cost for storage
            shut_down=0.0,  # PyPSA doesn't have shut down cost for storage
            energy_shortage_cost=0.0,  # PyPSA doesn't have energy shortage cost
            energy_surplus_cost=0.0,  # PyPSA doesn't have energy surplus cost
            charge_variable_cost=charge_variable_cost,
            discharge_variable_cost=discharge_variable_cost,
        )

    except Exception as e:
        logger.warning(f"Error creating storage cost for {pypsa_component.name}: {e}")
        return None
