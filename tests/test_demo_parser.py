"""Test script to ingest a real PyPSA network and convert to R2X format."""

import argparse
import logging
from pathlib import Path
from loguru import logger
from infrasys.component import Component

from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaStorageUnit, PypsaLink, PypsaLine, PypsaLoad, PypsaStore


def test_demo_parser(netcdf_file_path="tests/data/test_network.nc", verbose=False):
    """Demo function to parse a PyPSA network and convert to R2X format.
    
    Args:
        netcdf_file_path: Path to PyPSA NetCDF file
        verbose: Enable verbose logging
    """
    
    # Set up logging
    if verbose:
        logger.add("pypsa_parser.log", level="DEBUG")
    else:
        logger.add("pypsa_parser.log", level="INFO")
    
    # Resolve the file path relative to this script's location
    script_dir = Path(__file__).parent
    netcdf_file = script_dir / netcdf_file_path
    
    if not netcdf_file.exists():
        logger.error(f"NetCDF file not found: {netcdf_file}")
        if netcdf_file_path == "tests/data/test_network.nc":
            logger.error("The default test file 'tests/data/test_network.nc' was not found.")
            logger.error("Please provide a PyPSA network file using --netcdf-file-path /path/to/your/network.nc")
        return
    
    # Parse the network
    logger.info(f"Parsing PyPSA network from: {netcdf_file}")
    pypsa_parser = PypsaParser(netcdf_file=netcdf_file)
    
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
    links = list(system.get_components(PypsaLink))
    lines = list(system.get_components(PypsaLine))
    loads = list(system.get_components(PypsaLoad))
    stores = list(system.get_components(PypsaStore))
    logger.info(f"Buses: {len(buses)}")
    logger.info(f"Generators: {len(generators)}")
    logger.info(f"Storage Units: {len(storage_units)}")
    logger.info(f"Links: {len(links)}")
    logger.info(f"Lines: {len(lines)}")
    logger.info(f"Loads: {len(loads)}")
    logger.info(f"Stores: {len(stores)}")
    
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
    
    # Show first few links
    if links:
        logger.info("First 5 links:")
        for i, link in enumerate(links[:5]):
            logger.info(f"  {i+1}. {link.name} ({link.carrier}) - {link.p_nom} MW ({link.bus0} -> {link.bus1})")
    
    # Show first few lines
    if lines:
        logger.info("First 5 lines:")
        for i, line in enumerate(lines[:5]):
            logger.info(f"  {i+1}. {line.name} ({line.carrier}) - {line.s_nom} MVA ({line.bus0} -> {line.bus1})")
    
    # Show first few loads
    if loads:
        logger.info("First 5 loads:")
        for i, load in enumerate(loads[:5]):
            logger.info(f"  {i+1}. {load.name} ({load.carrier}) - {load.p_set} MW at {load.bus}")
    
    # Show first few stores
    if stores:
        logger.info("First 5 stores:")
        for i, store in enumerate(stores[:5]):
            logger.info(f"  {i+1}. {store.name} ({store.carrier}) - {store.e_nom} MWh at {store.bus}")
    
    logger.info("=== Conversion Complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse PyPSA network to R2X format")
    parser.add_argument("--netcdf-file-path", type=str, default="data/test_network.nc", help="Path to PyPSA NetCDF file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Resolve the file path relative to this script's location
    script_dir = Path(__file__).parent
    netcdf_file_path = script_dir / args.netcdf_file_path
    
    # Call the test function with parsed arguments
    test_demo_parser(netcdf_file_path=str(netcdf_file_path), verbose=args.verbose)