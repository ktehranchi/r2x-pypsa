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

from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaStorageUnit, PypsaLink, PypsaLine, PypsaLoad, PypsaStore, get_ts_or_static, get_series_only, safe_float, safe_str
from r2x_pypsa.models.property_values import PypsaProperty


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
        self._process_stores(system)
        self._process_links(system)
        self._process_lines(system)
        self._process_loads(system)
        
        
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
                    v_nom=PypsaProperty.create(value=safe_float(bus_data.get("v_nom", 1.0)), units="kV"),
                    type=PypsaProperty.create(value=safe_str(bus_data.get("type"))),
                    x=PypsaProperty.create(value=safe_float(bus_data.get("x", 0.0))),
                    y=PypsaProperty.create(value=safe_float(bus_data.get("y", 0.0))),
                    carrier=PypsaProperty.create(value=safe_str(bus_data.get("carrier", "AC"))),
                    unit=PypsaProperty.create(value=safe_str(bus_data.get("unit"))),
                    location=PypsaProperty.create(value=safe_str(bus_data.get("location"))),
                    v_mag_pu_min=PypsaProperty.create(value=safe_float(bus_data.get("v_mag_pu_min", 0.0))),
                    v_mag_pu_max=PypsaProperty.create(value=safe_float(bus_data.get("v_mag_pu_max", float('inf')))),
                    
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
        
        # Get time-varying data using get_switchable_as_dense
        available_attrs = set(self.network.generators.columns)
        nan_default_attrs = {'ramp_limit_up', 'ramp_limit_down'}
        
        # Normal attributes (always exist)
        p_min_pu_t = self.network.get_switchable_as_dense('Generator', 'p_min_pu')
        p_max_pu_t = self.network.get_switchable_as_dense('Generator', 'p_max_pu')
        p_set_t = self.network.get_switchable_as_dense('Generator', 'p_set')
        q_set_t = self.network.get_switchable_as_dense('Generator', 'q_set')
        marginal_cost_t = self.network.get_switchable_as_dense('Generator', 'marginal_cost')
        marginal_cost_quadratic_t = self.network.get_switchable_as_dense('Generator', 'marginal_cost_quadratic')
        efficiency_t = self.network.get_switchable_as_dense('Generator', 'efficiency')
        stand_by_cost_t = self.network.get_switchable_as_dense('Generator', 'stand_by_cost')
        
        # NaN default attributes (may not exist)
        ramp_limit_up_t = self.network.get_switchable_as_dense('Generator', 'ramp_limit_up') if 'ramp_limit_up' in available_attrs else None
        ramp_limit_down_t = self.network.get_switchable_as_dense('Generator', 'ramp_limit_down') if 'ramp_limit_down' in available_attrs else None
        
        # Series-only data will be accessed directly from network.generators.{attr}
        
        for gen_name, gen_data in self.network.generators.iterrows():
            try:
                # Create PyPSA generator component with all attributes
                generator = PypsaGenerator(
                    # Required attributes
                    name=gen_name,
                    bus=gen_data.get("bus", "unknown"),
                    
                    # Static attributes
                    control=PypsaProperty.create(value=gen_data.get("control", "PQ")),
                    type=PypsaProperty.create(value=safe_str(gen_data.get("type"))),
                    p_nom=PypsaProperty.create(value=safe_float(gen_data.get("p_nom", 0.0)), units="MW"),
                    p_nom_mod=PypsaProperty.create(value=safe_float(gen_data.get("p_nom_mod", 0.0)), units="MW"),
                    p_nom_extendable=PypsaProperty.create(value=bool(gen_data.get("p_nom_extendable", False))),
                    p_nom_min=PypsaProperty.create(value=safe_float(gen_data.get("p_nom_min", 0.0)), units="MW"),
                    p_nom_max=PypsaProperty.create(value=safe_float(gen_data.get("p_nom_max", float('inf'))), units="MW"),
                    e_sum_min=PypsaProperty.create(value=safe_float(gen_data.get("e_sum_min", float('-inf'))), units="MWh"),
                    e_sum_max=PypsaProperty.create(value=safe_float(gen_data.get("e_sum_max", float('inf'))), units="MWh"),
                    sign=PypsaProperty.create(value=safe_float(gen_data.get("sign", 1.0))),
                    carrier=PypsaProperty.create(value=safe_str(gen_data.get("carrier"))),
                    active=PypsaProperty.create(value=bool(gen_data.get("active", True))),
                    build_year=PypsaProperty.create(value=int(gen_data.get("build_year", 0))),
                    lifetime=PypsaProperty.create(value=safe_float(gen_data.get("lifetime", float('inf'))), units="years"),
                    capital_cost=PypsaProperty.create(value=safe_float(gen_data.get("capital_cost", 0.0)), units="usd/MW"),
                    
                    # Unit commitment attributes
                    committable=PypsaProperty.create(value=bool(gen_data.get("committable", False))),
                    start_up_cost=PypsaProperty.create(value=safe_float(gen_data.get("start_up_cost", 0.0)), units="usd"),
                    shut_down_cost=PypsaProperty.create(value=safe_float(gen_data.get("shut_down_cost", 0.0)), units="usd"),
                    min_up_time=PypsaProperty.create(value=int(gen_data.get("min_up_time", 0))),
                    min_down_time=PypsaProperty.create(value=int(gen_data.get("min_down_time", 0))),
                    up_time_before=PypsaProperty.create(value=int(gen_data.get("up_time_before", 1))),
                    down_time_before=PypsaProperty.create(value=int(gen_data.get("down_time_before", 0))),
                    ramp_limit_start_up=PypsaProperty.create(value=safe_float(gen_data.get("ramp_limit_start_up", 1.0))),
                    ramp_limit_shut_down=PypsaProperty.create(value=safe_float(gen_data.get("ramp_limit_shut_down", 1.0))),
                    weight=PypsaProperty.create(value=safe_float(gen_data.get("weight", 1.0))),
                    
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
                    control=PypsaProperty.create(value=storage_data.get("control", "PQ")),
                    type=PypsaProperty.create(value=safe_str(storage_data.get("type"))),
                    p_nom=PypsaProperty.create(value=safe_float(storage_data.get("p_nom", 0.0)), units="MW"),
                    p_nom_mod=PypsaProperty.create(value=safe_float(storage_data.get("p_nom_mod", 0.0)), units="MW"),
                    p_nom_extendable=PypsaProperty.create(value=bool(storage_data.get("p_nom_extendable", False))),
                    p_nom_min=PypsaProperty.create(value=safe_float(storage_data.get("p_nom_min", 0.0)), units="MW"),
                    p_nom_max=PypsaProperty.create(value=safe_float(storage_data.get("p_nom_max", float('inf'))), units="MW"),
                    sign=PypsaProperty.create(value=safe_float(storage_data.get("sign", 1.0))),
                    carrier=PypsaProperty.create(value=safe_str(storage_data.get("carrier"))),
                    capital_cost=PypsaProperty.create(value=safe_float(storage_data.get("capital_cost", 0.0)), units="usd/MW"),
                    active=PypsaProperty.create(value=bool(storage_data.get("active", True))),
                    build_year=PypsaProperty.create(value=int(storage_data.get("build_year", 0))),
                    lifetime=PypsaProperty.create(value=safe_float(storage_data.get("lifetime", float('inf'))), units="years"),
                    state_of_charge_initial=PypsaProperty.create(value=safe_float(storage_data.get("state_of_charge_initial", 0.0)), units="MWh"),
                    state_of_charge_initial_per_period=PypsaProperty.create(value=bool(storage_data.get("state_of_charge_initial_per_period", False))),
                    cyclic_state_of_charge=PypsaProperty.create(value=bool(storage_data.get("cyclic_state_of_charge", False))),
                    cyclic_state_of_charge_per_period=PypsaProperty.create(value=bool(storage_data.get("cyclic_state_of_charge_per_period", True))),
                    max_hours=PypsaProperty.create(value=safe_float(storage_data.get("max_hours", 1.0)), units="hours"),
                    
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
                    
                    
                )
                
                # Add storage unit to system
                system.add_component(storage_unit)
                logger.debug(f"Added storage unit {storage_name} with carrier {storage_data.get('carrier', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process storage unit {storage_name}: {e}")
                continue

    def _process_links(self, system: System) -> None:
        """Process PyPSA links and convert to R2X format."""
        if self.network is None:
            return
            
        logger.info(f"Processing {len(self.network.links)} links")
        
        # Get time-varying data using get_switchable_as_dense
        available_attrs = set(self.network.links.columns)
        nan_default_attrs = {'ramp_limit_up', 'ramp_limit_down'}
        
        # Normal attributes (always exist)
        efficiency_t = self.network.get_switchable_as_dense('Link', 'efficiency')
        p_min_pu_t = self.network.get_switchable_as_dense('Link', 'p_min_pu')
        p_max_pu_t = self.network.get_switchable_as_dense('Link', 'p_max_pu')
        marginal_cost_t = self.network.get_switchable_as_dense('Link', 'marginal_cost')
        marginal_cost_quadratic_t = self.network.get_switchable_as_dense('Link', 'marginal_cost_quadratic')
        stand_by_cost_t = self.network.get_switchable_as_dense('Link', 'stand_by_cost')
        p_set_t = self.network.get_switchable_as_dense('Link', 'p_set')
        
        # NaN default attributes (may not exist)
        ramp_limit_up_t = self.network.get_switchable_as_dense('Link', 'ramp_limit_up') if 'ramp_limit_up' in available_attrs else None
        ramp_limit_down_t = self.network.get_switchable_as_dense('Link', 'ramp_limit_down') if 'ramp_limit_down' in available_attrs else None
        
        for link_name, link_data in self.network.links.iterrows():
            try:
                # Create PyPSA link component with all attributes
                link = PypsaLink(
                    # Required attributes
                    name=link_name,
                    bus0=link_data.get("bus0", "unknown"),
                    bus1=link_data.get("bus1", "unknown"),
                    
                    # Static attributes
                    type=PypsaProperty.create(value=safe_str(link_data.get("type"))),
                    carrier=PypsaProperty.create(value=safe_str(link_data.get("carrier"))),
                    active=PypsaProperty.create(value=bool(link_data.get("active", True))),
                    build_year=PypsaProperty.create(value=int(link_data.get("build_year", 0))),
                    lifetime=PypsaProperty.create(value=safe_float(link_data.get("lifetime", float('inf'))), units="years"),
                    p_nom=PypsaProperty.create(value=safe_float(link_data.get("p_nom", 0.0)), units="MW"),
                    p_nom_mod=PypsaProperty.create(value=safe_float(link_data.get("p_nom_mod", 0.0)), units="MW"),
                    p_nom_extendable=PypsaProperty.create(value=bool(link_data.get("p_nom_extendable", False))),
                    p_nom_min=PypsaProperty.create(value=safe_float(link_data.get("p_nom_min", 0.0)), units="MW"),
                    p_nom_max=PypsaProperty.create(value=safe_float(link_data.get("p_nom_max", float('inf'))), units="MW"),
                    capital_cost=PypsaProperty.create(value=safe_float(link_data.get("capital_cost", 0.0)), units="usd/MW"),
                    length=PypsaProperty.create(value=safe_float(link_data.get("length", 0.0)), units="km"),
                    terrain_factor=PypsaProperty.create(value=safe_float(link_data.get("terrain_factor", 1.0))),
                    committable=PypsaProperty.create(value=bool(link_data.get("committable", False))),
                    start_up_cost=PypsaProperty.create(value=safe_float(link_data.get("start_up_cost", 0.0)), units="usd"),
                    shut_down_cost=PypsaProperty.create(value=safe_float(link_data.get("shut_down_cost", 0.0)), units="usd"),
                    min_up_time=PypsaProperty.create(value=int(link_data.get("min_up_time", 0))),
                    min_down_time=PypsaProperty.create(value=int(link_data.get("min_down_time", 0))),
                    up_time_before=PypsaProperty.create(value=int(link_data.get("up_time_before", 1))),
                    down_time_before=PypsaProperty.create(value=int(link_data.get("down_time_before", 0))),
                    ramp_limit_start_up=PypsaProperty.create(value=safe_float(link_data.get("ramp_limit_start_up", 1.0))),
                    ramp_limit_shut_down=PypsaProperty.create(value=safe_float(link_data.get("ramp_limit_shut_down", 1.0))),
                    
                    # Time-varying attributes
                    efficiency=get_ts_or_static(self.network, 'links_t', 'efficiency', link_name, efficiency_t, link_data, 1.0),
                    p_set=get_ts_or_static(self.network, 'links_t', 'p_set', link_name, p_set_t, link_data, float('nan')),
                    p_min_pu=get_ts_or_static(self.network, 'links_t', 'p_min_pu', link_name, p_min_pu_t, link_data, 0.0),
                    p_max_pu=get_ts_or_static(self.network, 'links_t', 'p_max_pu', link_name, p_max_pu_t, link_data, 1.0),
                    marginal_cost=get_ts_or_static(self.network, 'links_t', 'marginal_cost', link_name, marginal_cost_t, link_data, 0.0),
                    marginal_cost_quadratic=get_ts_or_static(self.network, 'links_t', 'marginal_cost_quadratic', link_name, marginal_cost_quadratic_t, link_data, 0.0),
                    stand_by_cost=get_ts_or_static(self.network, 'links_t', 'stand_by_cost', link_name, stand_by_cost_t, link_data, 0.0),
                    ramp_limit_up=get_ts_or_static(self.network, 'links_t', 'ramp_limit_up', link_name, ramp_limit_up_t, link_data, float('nan')),
                    ramp_limit_down=get_ts_or_static(self.network, 'links_t', 'ramp_limit_down', link_name, ramp_limit_down_t, link_data, float('nan')),
                    
                )
                
                # Add link to system
                system.add_component(link)
                logger.debug(f"Added link {link_name} from {link_data.get('bus0', 'unknown')} to {link_data.get('bus1', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process link {link_name}: {e}")
                continue

    def _process_lines(self, system: System) -> None:
        """Process PyPSA lines and convert to R2X format."""
        if self.network is None:
            return
            
        logger.info(f"Processing {len(self.network.lines)} lines")
        
        # Get time-varying data using get_switchable_as_dense
        s_max_pu_t = self.network.get_switchable_as_dense('Line', 's_max_pu')
        
        for line_name, line_data in self.network.lines.iterrows():
            try:
                # Create PyPSA line component with all attributes
                line = PypsaLine(
                    # Required attributes
                    name=line_name,
                    bus0=line_data.get("bus0", "unknown"),
                    bus1=line_data.get("bus1", "unknown"),
                    
                    # Static attributes
                    type=PypsaProperty.create(value=safe_str(line_data.get("type"))),
                    x=PypsaProperty.create(value=safe_float(line_data.get("x", 0.0))),
                    r=PypsaProperty.create(value=safe_float(line_data.get("r", 0.0))),
                    g=PypsaProperty.create(value=safe_float(line_data.get("g", 0.0))),
                    b=PypsaProperty.create(value=safe_float(line_data.get("b", 0.0))),
                    s_nom=PypsaProperty.create(value=safe_float(line_data.get("s_nom", 0.0))),
                    s_nom_mod=PypsaProperty.create(value=safe_float(line_data.get("s_nom_mod", 0.0))),
                    s_nom_extendable=PypsaProperty.create(value=bool(line_data.get("s_nom_extendable", False))),
                    s_nom_min=PypsaProperty.create(value=safe_float(line_data.get("s_nom_min", 0.0))),
                    s_nom_max=PypsaProperty.create(value=safe_float(line_data.get("s_nom_max", float('inf')))),
                    capital_cost=PypsaProperty.create(value=safe_float(line_data.get("capital_cost", 0.0))),
                    active=PypsaProperty.create(value=bool(line_data.get("active", True))),
                    build_year=PypsaProperty.create(value=int(line_data.get("build_year", 0))),
                    lifetime=PypsaProperty.create(value=safe_float(line_data.get("lifetime", float('inf'))), units="years"),
                    length=PypsaProperty.create(value=safe_float(line_data.get("length", 0.0)), units="km"),
                    carrier=PypsaProperty.create(value=safe_str(line_data.get("carrier", "AC"))),
                    terrain_factor=PypsaProperty.create(value=safe_float(line_data.get("terrain_factor", 1.0))),
                    num_parallel=PypsaProperty.create(value=safe_float(line_data.get("num_parallel", 1.0))),
                    v_ang_min=PypsaProperty.create(value=safe_float(line_data.get("v_ang_min", float('-inf'))), units="degrees"),
                    v_ang_max=PypsaProperty.create(value=safe_float(line_data.get("v_ang_max", float('inf'))), units="degrees"),
                    
                    # Time-varying attributes
                    s_max_pu=get_ts_or_static(self.network, 'lines_t', 's_max_pu', line_name, s_max_pu_t, line_data, 1.0),
                )
                
                # Add line to system
                system.add_component(line)
                logger.debug(f"Added line {line_name} from {line_data.get('bus0', 'unknown')} to {line_data.get('bus1', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process line {line_name}: {e}")
                continue

    def _process_loads(self, system: System) -> None:
        """Process PyPSA loads and convert to R2X format."""
        if self.network is None:
            return
            
        logger.info(f"Processing {len(self.network.loads)} loads")
        
        # Get time-varying data using get_switchable_as_dense
        p_set_t = self.network.get_switchable_as_dense('Load', 'p_set')
        q_set_t = self.network.get_switchable_as_dense('Load', 'q_set')
        
        for load_name, load_data in self.network.loads.iterrows():
            try:
                # Create PyPSA load component with all attributes
                load = PypsaLoad(
                    # Required attributes
                    name=load_name,
                    bus=load_data.get("bus", "unknown"),
                    
                    # Static attributes
                    carrier=PypsaProperty.create(value=safe_str(load_data.get("carrier"))),
                    type=PypsaProperty.create(value=safe_str(load_data.get("type"))),
                    sign=PypsaProperty.create(value=safe_float(load_data.get("sign", -1.0))),
                    active=PypsaProperty.create(value=bool(load_data.get("active", True))),
                    
                    # Time-varying attributes
                    p_set=get_ts_or_static(self.network, 'loads_t', 'p_set', load_name, p_set_t, load_data, 0.0),
                    q_set=get_ts_or_static(self.network, 'loads_t', 'q_set', load_name, q_set_t, load_data, 0.0),
                )
                
                # Add load to system
                system.add_component(load)
                logger.debug(f"Added load {load_name} at bus {load_data.get('bus', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process load {load_name}: {e}")
                continue

    def _process_stores(self, system: System) -> None:
        """Process PyPSA stores and convert to R2X format."""
        if self.network is None:
            return
            
        logger.info(f"Processing {len(self.network.stores)} stores")
        
        # Get time-varying data using get_switchable_as_dense
        available_attrs = set(self.network.stores.columns)
        nan_default_attrs = {'e_set'}
        
        # Normal attributes (always exist)
        e_min_pu_t = self.network.get_switchable_as_dense('Store', 'e_min_pu')
        e_max_pu_t = self.network.get_switchable_as_dense('Store', 'e_max_pu')
        q_set_t = self.network.get_switchable_as_dense('Store', 'q_set')
        marginal_cost_t = self.network.get_switchable_as_dense('Store', 'marginal_cost')
        marginal_cost_quadratic_t = self.network.get_switchable_as_dense('Store', 'marginal_cost_quadratic')
        marginal_cost_storage_t = self.network.get_switchable_as_dense('Store', 'marginal_cost_storage')
        standing_loss_t = self.network.get_switchable_as_dense('Store', 'standing_loss')
        p_set_t = self.network.get_switchable_as_dense('Store', 'p_set')
        
        # NaN default attributes (may not exist)
        e_set_t = self.network.get_switchable_as_dense('Store', 'e_set') if 'e_set' in available_attrs else None
        
        for store_name, store_data in self.network.stores.iterrows():
            try:
                # Create PyPSA store component with all attributes
                store = PypsaStore(
                    # Required attributes
                    name=store_name,
                    bus=store_data.get("bus", "unknown"),
                    
                    # Static attributes
                    type=PypsaProperty.create(value=safe_str(store_data.get("type"))),
                    carrier=PypsaProperty.create(value=safe_str(store_data.get("carrier"))),
                    e_nom=PypsaProperty.create(value=safe_float(store_data.get("e_nom", 0.0)), units="MWh"),
                    e_nom_mod=PypsaProperty.create(value=safe_float(store_data.get("e_nom_mod", 0.0)), units="MWh"),
                    e_nom_extendable=PypsaProperty.create(value=bool(store_data.get("e_nom_extendable", False))),
                    e_nom_min=PypsaProperty.create(value=safe_float(store_data.get("e_nom_min", 0.0)), units="MWh"),
                    e_nom_max=PypsaProperty.create(value=safe_float(store_data.get("e_nom_max", float('inf'))), units="MWh"),
                    e_initial=PypsaProperty.create(value=safe_float(store_data.get("e_initial", 0.0)), units="MWh"),
                    e_initial_per_period=PypsaProperty.create(value=bool(store_data.get("e_initial_per_period", False))),
                    e_cyclic=PypsaProperty.create(value=bool(store_data.get("e_cyclic", False))),
                    e_cyclic_per_period=PypsaProperty.create(value=bool(store_data.get("e_cyclic_per_period", True))),
                    sign=PypsaProperty.create(value=safe_float(store_data.get("sign", 1.0))),
                    capital_cost=PypsaProperty.create(value=safe_float(store_data.get("capital_cost", 0.0)), units="usd/MWh"),
                    active=PypsaProperty.create(value=bool(store_data.get("active", True))),
                    build_year=PypsaProperty.create(value=int(store_data.get("build_year", 0))),
                    lifetime=PypsaProperty.create(value=safe_float(store_data.get("lifetime", float('inf'))), units="years"),
                    
                    # Time-varying attributes
                    e_min_pu=get_ts_or_static(self.network, 'stores_t', 'e_min_pu', store_name, e_min_pu_t, store_data, 0.0),
                    e_max_pu=get_ts_or_static(self.network, 'stores_t', 'e_max_pu', store_name, e_max_pu_t, store_data, 1.0),
                    p_set=get_ts_or_static(self.network, 'stores_t', 'p_set', store_name, p_set_t, store_data, float('nan')),
                    q_set=get_ts_or_static(self.network, 'stores_t', 'q_set', store_name, q_set_t, store_data, 0.0),
                    e_set=get_ts_or_static(self.network, 'stores_t', 'e_set', store_name, e_set_t, store_data, float('nan')),
                    marginal_cost=get_ts_or_static(self.network, 'stores_t', 'marginal_cost', store_name, marginal_cost_t, store_data, 0.0),
                    marginal_cost_quadratic=get_ts_or_static(self.network, 'stores_t', 'marginal_cost_quadratic', store_name, marginal_cost_quadratic_t, store_data, 0.0),
                    marginal_cost_storage=get_ts_or_static(self.network, 'stores_t', 'marginal_cost_storage', store_name, marginal_cost_storage_t, store_data, 0.0),
                    standing_loss=get_ts_or_static(self.network, 'stores_t', 'standing_loss', store_name, standing_loss_t, store_data, 0.0),
                    
                )
                
                # Add store to system
                system.add_component(store)
                logger.debug(f"Added store {store_name} at bus {store_data.get('bus', 'unknown')}")
                
            except Exception as e:
                logger.warning(f"Failed to process store {store_name}: {e}")
                continue


