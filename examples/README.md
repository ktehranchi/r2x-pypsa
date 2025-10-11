# Examples

This directory contains example scripts demonstrating how to use the `r2x-pypsa` package.

## Available Examples

### convert_pypsa_to_sienna.py

A command-line script that converts PyPSA networks to Sienna JSON format.

**Usage:**
```bash
python convert_pypsa_to_sienna.py <input_netcdf> <output_json>
```

**Example:**
```bash
# Basic conversion
python convert_pypsa_to_sienna.py ../tests/data/test_network.nc output/sienna_system.json

# With verbose logging
python convert_pypsa_to_sienna.py ../tests/data/test_network.nc output/sienna_system.json --verbose
```

**What it does:**
1. Loads a PyPSA network from a NetCDF file
2. Parses all components (buses, generators, loads, lines, links, etc.)
3. Applies default component type mappings
4. Exports the system to Sienna JSON format
5. Creates accompanying time series data files

**Output files:**
- `sienna_system.json` - Main Sienna system file
- `time_series_storage.h5` - Time series data (HDF5 format)
- `time_series_storage_metadata.db` - Time series metadata (SQLite database)
- `conversion.log` - Detailed conversion log

## More Examples

For more detailed examples and use cases, see the [PyPSA to Sienna Conversion Guide](../PYPSA_TO_SIENNA.md).
