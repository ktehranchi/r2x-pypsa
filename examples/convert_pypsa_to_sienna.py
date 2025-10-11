#!/usr/bin/env python3
"""
Example script: Convert PyPSA network to Sienna JSON format

This script demonstrates how to:
1. Load a PyPSA network from a NetCDF file
2. Convert it to R2X System format
3. Export it to Sienna JSON format

Usage:
    python convert_pypsa_to_sienna.py <input_netcdf> <output_json>

Example:
    python convert_pypsa_to_sienna.py data/my_network.nc output/sienna_system.json
"""

import sys
import argparse
from pathlib import Path
from loguru import logger

from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization import pypsa_to_sienna, create_default_mapping
from r2x_pypsa.models import PypsaGenerator, PypsaBus, PypsaLoad, PypsaLine, PypsaLink
from infrasys.component import Component


def convert_network(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    """Convert a PyPSA network to Sienna JSON format.
    
    Args:
        input_path: Path to PyPSA NetCDF file
        output_path: Path where Sienna JSON will be saved
        verbose: Enable verbose logging
    """
    # Configure logging
    if verbose:
        logger.add("conversion.log", level="DEBUG")
        logger.info("Verbose logging enabled")
    else:
        logger.add("conversion.log", level="INFO")
    
    # Validate input file
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)
    
    if not input_path.suffix == ".nc":
        logger.warning(f"Input file does not have .nc extension: {input_path}")
    
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Parse PyPSA network
    logger.info(f"Parsing PyPSA network from: {input_path}")
    try:
        parser = PypsaParser(netcdf_file=str(input_path))
        system = parser.build_system()
    except Exception as e:
        logger.error(f"Failed to parse PyPSA network: {e}")
        sys.exit(1)
    
    # Log summary of parsed components
    logger.info("=== PyPSA Network Summary ===")
    total_components = len(list(system.get_components(Component)))
    buses = len(list(system.get_components(PypsaBus)))
    generators = len(list(system.get_components(PypsaGenerator)))
    loads = len(list(system.get_components(PypsaLoad)))
    lines = len(list(system.get_components(PypsaLine)))
    links = len(list(system.get_components(PypsaLink)))
    
    logger.info(f"Total components: {total_components}")
    logger.info(f"  - Buses: {buses}")
    logger.info(f"  - Generators: {generators}")
    logger.info(f"  - Loads: {loads}")
    logger.info(f"  - Lines: {lines}")
    logger.info(f"  - Links: {links}")
    
    # Step 2: Create mapping configuration
    logger.info("Creating component mapping configuration")
    mapping = create_default_mapping()
    
    # Step 3: Convert to Sienna JSON
    logger.info(f"Converting to Sienna format: {output_path}")
    try:
        pypsa_to_sienna(
            pypsa_system=system,
            output_path=str(output_path),
            mapping=mapping
        )
    except Exception as e:
        logger.error(f"Failed to convert to Sienna format: {e}")
        sys.exit(1)
    
    # Success!
    logger.info("=== Conversion Complete ===")
    logger.info(f"Sienna system saved to: {output_path}")
    logger.info(f"Time series data: {output_path.parent / 'time_series_storage.h5'}")
    logger.info(f"Time series metadata: {output_path.parent / 'time_series_storage_metadata.db'}")
    
    # Verify output files exist
    if output_path.exists():
        logger.info(f"✓ Output file size: {output_path.stat().st_size / 1024:.2f} KB")
    else:
        logger.warning("⚠ Output file was not created")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert PyPSA network to Sienna JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s data/network.nc output/sienna_system.json
  %(prog)s data/network.nc output/sienna_system.json --verbose
        """
    )
    
    parser.add_argument(
        "input",
        type=Path,
        help="Path to PyPSA NetCDF file (.nc)"
    )
    
    parser.add_argument(
        "output",
        type=Path,
        help="Path where Sienna JSON will be saved (.json)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Run conversion
    convert_network(
        input_path=args.input,
        output_path=args.output,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
