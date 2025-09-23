import pypsa
import pandas as pd
from r2x.plugin_manager import PluginManager
from r2x.api import System
from r2x.parser.handler import BaseParser
from argparse import ArgumentParser
from pathlib import Path
from typing import Optional
from loguru import logger
from uuid import uuid4
from infrasys.component import Component


class PypsaGenerator(Component):
    """PyPSA Generator component."""

    name: str
    bus: str
    carrier: str
    p_nom: float = 0.0
    p_nom_extendable: bool = False
    marginal_cost: float = 0.0
    capital_cost: float = 0.0
    efficiency: float = 1.0
    p_max_pu: float = 1.0
    p_min_pu: float = 0.0


@PluginManager.register_cli("parser", "r2x_pypsaParser")
def cli_arguments(parser: ArgumentParser):
    """CLI arguments for the PyPSA parser."""
    parser.add_argument(
        "--netcdf-file-path",
        type=str,
        required=True,
        dest="netcdf_file",
        help="Path to the PyPSA netcdf file",
    )
    parser.add_argument(
        "--weather-year",
        type=int,
        dest="weather_year",
        help="Custom weather year argument",
    )


class PypsaParser(BaseParser):
    """Parser for PyPSA networks to R2X System format."""
    
    def __init__(self, netcdf_file: str | Path, weather_year: Optional[int] = None):
        self.netcdf_file = Path(netcdf_file)
        self.weather_year = weather_year
        self.network: Optional[pypsa.Network] = None
        
    def build_system(self) -> System:
        """Build R2X System from PyPSA network."""
        if not self.netcdf_file.exists():
            raise FileNotFoundError(f"PyPSA netcdf file not found: {self.netcdf_file}")
            
        logger.info(f"Loading PyPSA network from: {self.netcdf_file}")
        
        # Load PyPSA network
        self.network = pypsa.Network(str(self.netcdf_file))
        
        # Create R2X system
        system = System()

        # Process generators (focus-only)
        self._process_generators(system)
        
        logger.info(f"Successfully created R2X system with {len(list(system.get_components(Component)))} components")
        return system
    
    def _process_generators(self, system: System) -> None:
        """Process PyPSA generators and convert to R2X format."""
        if self.network is None:
            return
            
        logger.info(f"Processing {len(self.network.generators)} generators")
        
        for gen_name, gen_data in self.network.generators.iterrows():
            try:
                # Create PyPSA generator component
                generator = PypsaGenerator(
                    name=gen_name,
                    bus=gen_data.get("bus", "unknown"),
                    carrier=gen_data.get("carrier", "unknown"),
                    p_nom=float(gen_data.get("p_nom", 0.0)) if not pd.isna(gen_data.get("p_nom", 0.0)) else 0.0,
                    p_nom_extendable=bool(gen_data.get("p_nom_extendable", False)),
                    marginal_cost=float(gen_data.get("marginal_cost", 0.0)) if not pd.isna(gen_data.get("marginal_cost", 0.0)) else 0.0,
                    capital_cost=float(gen_data.get("capital_cost", 0.0)) if not pd.isna(gen_data.get("capital_cost", 0.0)) else 0.0,
                    efficiency=float(gen_data.get("efficiency", 1.0)) if not pd.isna(gen_data.get("efficiency", 1.0)) else 1.0,
                    p_max_pu=float(gen_data.get("p_max_pu", 1.0)) if not pd.isna(gen_data.get("p_max_pu", 1.0)) else 1.0,
                    p_min_pu=float(gen_data.get("p_min_pu", 0.0)) if not pd.isna(gen_data.get("p_min_pu", 0.0)) else 0.0,
                )
                
                # Add generator to system
                system.add_component(generator)
                logger.debug(f"Added generator {gen_name} with carrier {gen_data.get('carrier', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process generator {gen_name}: {e}")
                continue
    


def main():
    """Main function to demonstrate the PyPSA parser."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PyPSA to R2X Parser")
    cli_arguments(parser)
    args = parser.parse_args()
    
    # Create parser instance
    pypsa_parser = PypsaParser(
        netcdf_file=args.netcdf_file,
        weather_year=args.weather_year
    )
    
    # Build R2X system
    system = pypsa_parser.build_system()
    
    # Log summary
    logger.info("=== PyPSA to R2X Conversion Summary ===")
    
    # Get all components using the base Component class
    all_components = list(system.get_components(Component))
    logger.info(f"Total components: {len(all_components)}")

    # Count by type (generators only)
    generators = list(system.get_components(PypsaGenerator))
    logger.info(f"Generators: {len(generators)}")
    
    # Show first few generators
    if generators:
        logger.info("First 5 generators:")
        for i, gen in enumerate(generators[:5]):
            logger.info(f"  {i+1}. {gen.name} ({gen.carrier}) - {gen.p_nom} MW")
    return system


if __name__ == "__main__":
    main()
