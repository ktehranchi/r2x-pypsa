"""API for PyPSA to Sienna serialization."""

from pathlib import Path
from typing import Any, Dict

from loguru import logger
from r2x.api import System
from r2x.models import (
    ThermalStandard,
    RenewableDispatch,
    HydroDispatch,
    EnergyReservoirStorage,
    HydroPumpedStorage,
)
from r2x.enums import PrimeMoversType, ThermalFuels
from infrasys import TimeSeriesStorageType

from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization.to_sienna import infrasys_to_psy


def pypsa_to_sienna(
    pypsa_system: System,
    output_path: Path | str,
    mapping: Dict[str, Any] | None = None,
    **kwargs
) -> None:
    """Convert a PyPSA system to Sienna format.

    Parameters
    ----------
    pypsa_system : System
        The PyPSA system to convert
    output_path : Path | str
        Path where to save the Sienna JSON file
    mapping : Dict[str, Any] | None
        Mapping configuration for component conversion
    **kwargs
        Additional arguments passed to the serialization functions
    """
    logger.info("Converting PyPSA system to Sienna format")
    
    # Create a new PSY system
    psy_system = System(
        name="PSY system",
        auto_add_composed_components=True,
        time_series_storage_type=TimeSeriesStorageType.HDF5
    )
    
    # Convert all PyPSA components to PSY components
    for component in pypsa_system._component_mgr.iter_all():
        try:
            pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
        except Exception as e:
            logger.warning(f"Failed to convert component {component.name}: {e}")
            continue
    
    # Serialize the PSY system to Sienna format
    infrasys_to_psy(psy_system, filename=output_path, **kwargs)
    
    logger.info(f"Sienna system saved to {output_path}")


def create_default_mapping() -> Dict[str, Any]:
    """Create a default mapping configuration for PyPSA to PSY conversion.
    
    Based on PyPSA's standard carrier naming conventions.

    Returns
    -------
    Dict[str, Any]
        Default mapping configuration
    """
    return {
        "generator_mapping": {
            # Standard PyPSA carriers (from PyPSA examples and documentation)
            "coal": ThermalStandard,
            "gas": ThermalStandard, 
            "nuclear": ThermalStandard,
            "oil": ThermalStandard,
            "biomass": ThermalStandard,
            "waste": ThermalStandard,
            "geothermal": ThermalStandard,
            
            # Renewable carriers
            "solar": RenewableDispatch,
            "onwind": RenewableDispatch,
            "offwind": RenewableDispatch,
            "offwind_floating": RenewableDispatch, 
            "hydro": HydroDispatch,
            
            # Storage carriers
            "battery": EnergyReservoirStorage,
            "pumped_hydro": HydroPumpedStorage,
            
            # Gas turbine variants (common in PyPSA examples)
            "OCGT": ThermalStandard,  # Open Cycle Gas Turbine
            "CCGT": ThermalStandard,  # Combined Cycle Gas Turbine
            
            # Other common carriers
            "other": ThermalStandard,
        },
        "prime_mover_mapping": {
            # Map to standard prime mover types
            "coal": PrimeMoversType.ST,  # Steam Turbine
            "gas": PrimeMoversType.GT,   # Gas Turbine
            "nuclear": PrimeMoversType.ST,  # Steam Turbine
            "oil": PrimeMoversType.IC,   # Internal Combustion
            "biomass": PrimeMoversType.BT,  # Biomass Turbine
            "waste": PrimeMoversType.ST,  # Steam Turbine
            "geothermal": PrimeMoversType.OT,  # Other
            "solar": PrimeMoversType.PVe,  # Photovoltaic
            "onwind": PrimeMoversType.WT,   # Wind Turbine
            "offwind": PrimeMoversType.WT,  # Wind Turbine
            "offwind_floating": PrimeMoversType.WT,  # Wind Turbine
            "hydro": PrimeMoversType.HY,  # Hydro
            "battery": PrimeMoversType.BA,  # Battery
            "pumped_hydro": PrimeMoversType.HY,  # Hydro
            "OCGT": PrimeMoversType.GT,  # Gas Turbine
            "CCGT": PrimeMoversType.GT,  # Gas Turbine
            "other": PrimeMoversType.OT,  # Other
        },
        "fuel_mapping": {
            # Map to standard fuel types
            "coal": ThermalFuels.COAL,
            "gas": ThermalFuels.NATURAL_GAS,
            "nuclear": ThermalFuels.NUCLEAR,
            "oil": ThermalFuels.DISTILLATE_FUEL_OIL,
            "biomass": ThermalFuels.OTHER,
            "waste": ThermalFuels.OTHER,
            "geothermal": ThermalFuels.GEOTHERMAL,
            "solar": ThermalFuels.OTHER,
            "onwind": ThermalFuels.OTHER,
            "offwind": ThermalFuels.OTHER,
            "offwind_floating": ThermalFuels.OTHER,
            "hydro": ThermalFuels.OTHER,
            "battery": ThermalFuels.OTHER,
            "pumped_hydro": ThermalFuels.OTHER,
            "OCGT": ThermalFuels.NATURAL_GAS,
            "CCGT": ThermalFuels.NATURAL_GAS,
            "other": ThermalFuels.OTHER,
        },
    }


def convert_pypsa_network(
    pypsa_network,
    output_path: Path | str,
    mapping: Dict[str, Any] | None = None,
    **kwargs
) -> None:
    """Convert a PyPSA network object to Sienna format.

    This is a convenience function that works directly with PyPSA network objects.

    Parameters
    ----------
    pypsa_network
        A PyPSA network object
    output_path : Path | str
        Path where to save the Sienna JSON file
    mapping : Dict[str, Any] | None
        Mapping configuration for component conversion
    **kwargs
        Additional arguments passed to the serialization functions
    """
    # This would need to be implemented to convert PyPSA network to r2x System
    # For now, this is a placeholder
    raise NotImplementedError(
        "Direct PyPSA network conversion not yet implemented. "
        "Please use pypsa_to_sienna with an r2x System object."
    )
