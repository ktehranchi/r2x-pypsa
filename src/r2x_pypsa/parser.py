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

from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaStorageUnit, get_ts_or_static, get_series_only, safe_float, safe_str


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

        # Process buses, generators, and storage units
        self._process_buses(system)
        self._process_generators(system)
        self._process_storage_units(system)
        
        logger.info(f"Successfully created R2X system with {len(list(system.get_components(Component)))} components")
        return system
    
    def _process_buses(self, system: System) -> None:
        """Process PyPSA buses and convert to R2X format."""
        if self.network is None:
            return
            
        logger.info(f"Processing {len(self.network.buses)} buses")
        
        # Get time-varying data using get_switchable_as_dense for buses
        v_mag_pu_set_t = self.network.get_switchable_as_dense('Bus', 'v_mag_pu_set')
        
        for bus_name, bus_data in self.network.buses.iterrows():
            try:
                # Create PyPSA bus component with all attributes
                bus = PypsaBus(
                    # Required attributes
                    name=bus_name,
                    
                    # Static attributes
                    v_nom=safe_float(bus_data.get("v_nom", 1.0)),
                    type=safe_str(bus_data.get("type")),
                    x=safe_float(bus_data.get("x", 0.0)),
                    y=safe_float(bus_data.get("y", 0.0)),
                    carrier=safe_str(bus_data.get("carrier", "AC")),
                    unit=safe_str(bus_data.get("unit")),
                    location=safe_str(bus_data.get("location")),
                    v_mag_pu_min=safe_float(bus_data.get("v_mag_pu_min", 0.0)),
                    v_mag_pu_max=safe_float(bus_data.get("v_mag_pu_max", float('inf'))),
                    
                    # Time-varying attributes (prefer time series if populated; else static scalar)
                    v_mag_pu_set=get_ts_or_static(self.network, 'buses_t', 'v_mag_pu_set', bus_name, v_mag_pu_set_t, bus_data, 1.0),
                    
                )
                
                # Add bus to system
                system.add_component(bus)
                logger.debug(f"Added bus {bus_name} with carrier {bus_data.get('carrier', 'AC')}")
                
            except Exception as e:
                logger.warning(f"Failed to process bus {bus_name}: {e}")
                continue
    
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
                    
                    
                    # Output attributes (from optimization)
                    p_nom_opt=safe_float(gen_data.get("p_nom_opt", 0.0)),
                )
                
                # Add generator to system
                system.add_component(generator)
                logger.debug(f"Added generator {gen_name} with carrier {gen_data.get('carrier', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process generator {gen_name}: {e}")
                continue
    
    def _process_storage_units(self, system: System) -> None:
        """Process PyPSA storage units and convert to R2X format."""
        if self.network is None:
            return
            
        logger.info(f"Processing {len(self.network.storage_units)} storage units")
        
        # Get time-varying data using get_switchable_as_dense
        # Attributes with NaN defaults may not exist in the network, so check for those
        available_attrs = set(self.network.storage_units.columns)
        nan_default_attrs = {'p_set', 'p_dispatch_set', 'p_store_set', 'state_of_charge_set'}
        
        # Normal attributes (always exist)
        p_min_pu_t = self.network.get_switchable_as_dense('StorageUnit', 'p_min_pu')
        p_max_pu_t = self.network.get_switchable_as_dense('StorageUnit', 'p_max_pu')
        q_set_t = self.network.get_switchable_as_dense('StorageUnit', 'q_set')
        spill_cost_t = self.network.get_switchable_as_dense('StorageUnit', 'spill_cost')
        marginal_cost_t = self.network.get_switchable_as_dense('StorageUnit', 'marginal_cost')
        marginal_cost_quadratic_t = self.network.get_switchable_as_dense('StorageUnit', 'marginal_cost_quadratic')
        marginal_cost_storage_t = self.network.get_switchable_as_dense('StorageUnit', 'marginal_cost_storage')
        efficiency_store_t = self.network.get_switchable_as_dense('StorageUnit', 'efficiency_store')
        efficiency_dispatch_t = self.network.get_switchable_as_dense('StorageUnit', 'efficiency_dispatch')
        standing_loss_t = self.network.get_switchable_as_dense('StorageUnit', 'standing_loss')
        inflow_t = self.network.get_switchable_as_dense('StorageUnit', 'inflow')
        
        # NaN default attributes (may not exist)
        p_set_t = self.network.get_switchable_as_dense('StorageUnit', 'p_set') if 'p_set' in available_attrs else None
        p_dispatch_set_t = self.network.get_switchable_as_dense('StorageUnit', 'p_dispatch_set') if 'p_dispatch_set' in available_attrs else None
        p_store_set_t = self.network.get_switchable_as_dense('StorageUnit', 'p_store_set') if 'p_store_set' in available_attrs else None
        state_of_charge_set_t = self.network.get_switchable_as_dense('StorageUnit', 'state_of_charge_set') if 'state_of_charge_set' in available_attrs else None
        
        for storage_name, storage_data in self.network.storage_units.iterrows():
            try:
                # Create PyPSA storage unit component with all attributes
                storage_unit = PypsaStorageUnit(
                    # Required attributes
                    name=storage_name,
                    bus=storage_data.get("bus", "unknown"),
                    
                    # Static attributes
                    control=storage_data.get("control", "PQ"),
                    type=safe_str(storage_data.get("type")),
                    p_nom=safe_float(storage_data.get("p_nom", 0.0)),
                    p_nom_mod=safe_float(storage_data.get("p_nom_mod", 0.0)),
                    p_nom_extendable=bool(storage_data.get("p_nom_extendable", False)),
                    p_nom_min=safe_float(storage_data.get("p_nom_min", 0.0)),
                    p_nom_max=safe_float(storage_data.get("p_nom_max", float('inf'))),
                    sign=safe_float(storage_data.get("sign", 1.0)),
                    carrier=safe_str(storage_data.get("carrier")),
                    capital_cost=safe_float(storage_data.get("capital_cost", 0.0)),
                    active=bool(storage_data.get("active", True)),
                    build_year=int(storage_data.get("build_year", 0)),
                    lifetime=safe_float(storage_data.get("lifetime", float('inf'))),
                    state_of_charge_initial=safe_float(storage_data.get("state_of_charge_initial", 0.0)),
                    state_of_charge_initial_per_period=bool(storage_data.get("state_of_charge_initial_per_period", False)),
                    cyclic_state_of_charge=bool(storage_data.get("cyclic_state_of_charge", False)),
                    cyclic_state_of_charge_per_period=bool(storage_data.get("cyclic_state_of_charge_per_period", True)),
                    max_hours=safe_float(storage_data.get("max_hours", 1.0)),
                    
                    # Time-varying attributes (prefer time series if populated; else static scalar)
                    p_min_pu=get_ts_or_static(self.network, 'storage_units_t', 'p_min_pu', storage_name, p_min_pu_t, storage_data, -1.0),
                    p_max_pu=get_ts_or_static(self.network, 'storage_units_t', 'p_max_pu', storage_name, p_max_pu_t, storage_data, 1.0),
                    p_set=get_ts_or_static(self.network, 'storage_units_t', 'p_set', storage_name, p_set_t, storage_data, float('nan')),
                    q_set=get_ts_or_static(self.network, 'storage_units_t', 'q_set', storage_name, q_set_t, storage_data, 0.0),
                    p_dispatch_set=get_ts_or_static(self.network, 'storage_units_t', 'p_dispatch_set', storage_name, p_dispatch_set_t, storage_data, float('nan')),
                    p_store_set=get_ts_or_static(self.network, 'storage_units_t', 'p_store_set', storage_name, p_store_set_t, storage_data, float('nan')),
                    spill_cost=get_ts_or_static(self.network, 'storage_units_t', 'spill_cost', storage_name, spill_cost_t, storage_data, 0.0),
                    marginal_cost=get_ts_or_static(self.network, 'storage_units_t', 'marginal_cost', storage_name, marginal_cost_t, storage_data, 0.0),
                    marginal_cost_quadratic=get_ts_or_static(self.network, 'storage_units_t', 'marginal_cost_quadratic', storage_name, marginal_cost_quadratic_t, storage_data, 0.0),
                    marginal_cost_storage=get_ts_or_static(self.network, 'storage_units_t', 'marginal_cost_storage', storage_name, marginal_cost_storage_t, storage_data, 0.0),
                    state_of_charge_set=get_ts_or_static(self.network, 'storage_units_t', 'state_of_charge_set', storage_name, state_of_charge_set_t, storage_data, float('nan')),
                    efficiency_store=get_ts_or_static(self.network, 'storage_units_t', 'efficiency_store', storage_name, efficiency_store_t, storage_data, 1.0),
                    efficiency_dispatch=get_ts_or_static(self.network, 'storage_units_t', 'efficiency_dispatch', storage_name, efficiency_dispatch_t, storage_data, 1.0),
                    standing_loss=get_ts_or_static(self.network, 'storage_units_t', 'standing_loss', storage_name, standing_loss_t, storage_data, 0.0),
                    inflow=get_ts_or_static(self.network, 'storage_units_t', 'inflow', storage_name, inflow_t, storage_data, 0.0),
                    
                    
                    # Output attributes (from optimization)
                    p_nom_opt=safe_float(storage_data.get("p_nom_opt", 0.0)),
                )
                
                # Add storage unit to system
                system.add_component(storage_unit)
                logger.debug(f"Added storage unit {storage_name} with carrier {storage_data.get('carrier', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process storage unit {storage_name}: {e}")
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

    # Count by type
    buses = list(system.get_components(PypsaBus))
    generators = list(system.get_components(PypsaGenerator))
    storage_units = list(system.get_components(PypsaStorageUnit))
    logger.info(f"Buses: {len(buses)}")
    logger.info(f"Generators: {len(generators)}")
    logger.info(f"Storage Units: {len(storage_units)}")
    
    # Show first few buses
    if buses:
        logger.info("First 5 buses:")
        for i, bus in enumerate(buses[:5]):
            logger.info(f"  {i+1}. {bus.name} ({bus.carrier}) - {bus.v_nom} kV")
    
    # Show first few generators
    if generators:
        logger.info("First 5 generators:")
        for i, gen in enumerate(generators[:5]):
            logger.info(f"  {i+1}. {gen.name} ({gen.carrier}) - {gen.p_nom} MW")
    
    # Show first few storage units
    if storage_units:
        logger.info("First 5 storage units:")
        for i, storage in enumerate(storage_units[:5]):
            logger.info(f"  {i+1}. {storage.name} ({storage.carrier}) - {storage.p_nom} MW")
    return system


if __name__ == "__main__":
    main()
