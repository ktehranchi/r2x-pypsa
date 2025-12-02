#!/usr/bin/env python3
"""Simple script to plot Sienna dispatch results."""

from pathlib import Path
import sys

# Add parent directory to path to import helpers
sys.path.insert(0, str(Path(__file__).parent))

from helpers import plot_sienna_energy_balance

if __name__ == "__main__":
    # Default path
    dispatch_file = Path(__file__).parent / "test_output" / "sienna_dispatch.csv"
    
    # Allow command-line argument
    if len(sys.argv) > 1:
        dispatch_file = Path(sys.argv[1])
    
    if not dispatch_file.exists():
        print(f"Error: Dispatch file not found: {dispatch_file}")
        print("\nTo generate it, run:")
        print("  julia tests/run_sienna_ed.jl tests/test_output/elec_s380_c7a_ec_lv1_output_optimized.json tests/test_output/sienna_objective.txt")
        sys.exit(1)
    
    print(f"Plotting Sienna dispatch from: {dispatch_file}")
    # Plot 1 week (7*24 = 168 hours) to match PyPSA
    plot_sienna_energy_balance(dispatch_file, timesteps=7*24, label="Sienna")

