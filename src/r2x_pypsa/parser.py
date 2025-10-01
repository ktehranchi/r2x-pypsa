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

from r2x_pypsa.models import PypsaGenerator, get_ts_or_static, get_series_only, safe_float, safe_str


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
        
        # Get all time-varying data using get_switchable_as_dense (handles static vs time-varying automatically)
        p_min_pu_t = self.network.get_switchable_as_dense('Generator', 'p_min_pu')
        p_max_pu_t = self.network.get_switchable_as_dense('Generator', 'p_max_pu')
        p_set_t = self.network.get_switchable_as_dense('Generator', 'p_set')
        q_set_t = self.network.get_switchable_as_dense('Generator', 'q_set')
        marginal_cost_t = self.network.get_switchable_as_dense('Generator', 'marginal_cost')
        marginal_cost_quadratic_t = self.network.get_switchable_as_dense('Generator', 'marginal_cost_quadratic')
        efficiency_t = self.network.get_switchable_as_dense('Generator', 'efficiency')
        stand_by_cost_t = self.network.get_switchable_as_dense('Generator', 'stand_by_cost')
        ramp_limit_up_t = self.network.get_switchable_as_dense('Generator', 'ramp_limit_up')
        ramp_limit_down_t = self.network.get_switchable_as_dense('Generator', 'ramp_limit_down')
        
        # Series-only data will be accessed directly from network.generators.{attr}
        
        for gen_name, gen_data in self.network.generators.iterrows():
            try:
                # Create PyPSA generator component with all attributes
                generator = PypsaGenerator(
                    # Required attributes
                    name=gen_name,
                    bus=gen_data.get("bus", "unknown"),
                    
                    # Static attributes
                    control=gen_data.get("control", "PQ"),
                    type=safe_str(gen_data.get("type")),
                    p_nom=safe_float(gen_data.get("p_nom", 0.0)),
                    p_nom_mod=safe_float(gen_data.get("p_nom_mod", 0.0)),
                    p_nom_extendable=bool(gen_data.get("p_nom_extendable", False)),
                    p_nom_min=safe_float(gen_data.get("p_nom_min", 0.0)),
                    p_nom_max=safe_float(gen_data.get("p_nom_max", float('inf'))),
                    e_sum_min=safe_float(gen_data.get("e_sum_min", float('-inf'))),
                    e_sum_max=safe_float(gen_data.get("e_sum_max", float('inf'))),
                    sign=safe_float(gen_data.get("sign", 1.0)),
                    carrier=safe_str(gen_data.get("carrier")),
                    active=bool(gen_data.get("active", True)),
                    build_year=int(gen_data.get("build_year", 0)),
                    lifetime=safe_float(gen_data.get("lifetime", float('inf'))),
                    capital_cost=safe_float(gen_data.get("capital_cost", 0.0)),
                    
                    # Unit commitment attributes
                    committable=bool(gen_data.get("committable", False)),
                    start_up_cost=safe_float(gen_data.get("start_up_cost", 0.0)),
                    shut_down_cost=safe_float(gen_data.get("shut_down_cost", 0.0)),
                    min_up_time=int(gen_data.get("min_up_time", 0)),
                    min_down_time=int(gen_data.get("min_down_time", 0)),
                    up_time_before=int(gen_data.get("up_time_before", 1)),
                    down_time_before=int(gen_data.get("down_time_before", 0)),
                    ramp_limit_start_up=safe_float(gen_data.get("ramp_limit_start_up", 1.0)),
                    ramp_limit_shut_down=safe_float(gen_data.get("ramp_limit_shut_down", 1.0)),
                    weight=safe_float(gen_data.get("weight", 1.0)),
                    
                    # Time-varying attributes (prefer time series if populated; else static scalar)
                    p_min_pu=get_ts_or_static(self.network, 'generators_t', 'p_min_pu', gen_name, p_min_pu_t, gen_data, 0.0),
                    p_max_pu=get_ts_or_static(self.network, 'generators_t', 'p_max_pu', gen_name, p_max_pu_t, gen_data, 1.0),
                    p_set=get_ts_or_static(self.network, 'generators_t', 'p_set', gen_name, p_set_t, gen_data, 0.0),
                    q_set=get_ts_or_static(self.network, 'generators_t', 'q_set', gen_name, q_set_t, gen_data, 0.0),
                    marginal_cost=get_ts_or_static(self.network, 'generators_t', 'marginal_cost', gen_name, marginal_cost_t, gen_data, 0.0),
                    marginal_cost_quadratic=get_ts_or_static(self.network, 'generators_t', 'marginal_cost_quadratic', gen_name, marginal_cost_quadratic_t, gen_data, 0.0),
                    efficiency=get_ts_or_static(self.network, 'generators_t', 'efficiency', gen_name, efficiency_t, gen_data, 1.0),
                    stand_by_cost=get_ts_or_static(self.network, 'generators_t', 'stand_by_cost', gen_name, stand_by_cost_t, gen_data, 0.0),
                    ramp_limit_up=get_ts_or_static(self.network, 'generators_t', 'ramp_limit_up', gen_name, ramp_limit_up_t, gen_data, float('nan')),
                    ramp_limit_down=get_ts_or_static(self.network, 'generators_t', 'ramp_limit_down', gen_name, ramp_limit_down_t, gen_data, float('nan')),
                    
                    # Series-only attributes (always time series, never static)
                    p=get_series_only(self.network, gen_name, 'p', 0.0),
                    q=get_series_only(self.network, gen_name, 'q', 0.0),
                    status=get_series_only(self.network, gen_name, 'status', 1.0),
                    start_up=get_series_only(self.network, gen_name, 'start_up', 0.0),
                    shut_down=get_series_only(self.network, gen_name, 'shut_down', 0.0),
                    mu_upper=get_series_only(self.network, gen_name, 'mu_upper', 0.0),
                    mu_lower=get_series_only(self.network, gen_name, 'mu_lower', 0.0),
                    mu_p_set=get_series_only(self.network, gen_name, 'mu_p_set', 0.0),
                    mu_ramp_limit_up=get_series_only(self.network, gen_name, 'mu_ramp_limit_up', 0.0),
                    mu_ramp_limit_down=get_series_only(self.network, gen_name, 'mu_ramp_limit_down', 0.0),
                    
                    # Output attributes (from optimization)
                    p_nom_opt=safe_float(gen_data.get("p_nom_opt", 0.0)),
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
