#!/usr/bin/env python3
"""Inspect cost data in PyPSA network and PowerSystems system."""

import pypsa
from pathlib import Path
from r2x.api import System
from infrasys import TimeSeriesStorageType
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization import create_default_mapping
from r2x_pypsa.serialization.cost_models import create_operational_cost

def inspect_pypsa_costs(network):
    """Inspect cost data in PyPSA network."""
    print("=" * 80)
    print("PYPSA NETWORK COSTS")
    print("=" * 80)
    
    # Check generators
    if hasattr(network, 'generators') and not network.generators.empty:
        print(f"\nGenerators ({len(network.generators)}):")
        print("-" * 80)
        
        # Check for startup/shutdown costs
        has_startup = 'start_up_cost' in network.generators.columns
        has_shutdown = 'shut_down_cost' in network.generators.columns
        
        print(f"Has start_up_cost column: {has_startup}")
        print(f"Has shut_down_cost column: {has_shutdown}")
        
        if has_startup:
            startup_costs = network.generators['start_up_cost']
            non_zero_startup = startup_costs[startup_costs > 0]
            print(f"\nStartup costs:")
            print(f"  Total generators: {len(startup_costs)}")
            print(f"  Non-zero startup costs: {len(non_zero_startup)}")
            if len(non_zero_startup) > 0:
                print(f"  Min: ${startup_costs.min():,.2f}")
                print(f"  Max: ${startup_costs.max():,.2f}")
                print(f"  Mean: ${startup_costs.mean():,.2f}")
                print(f"  Sum: ${startup_costs.sum():,.2f}")
                print(f"\n  Sample generators with startup costs:")
                for idx in non_zero_startup.head(10).index:
                    print(f"    {idx}: ${startup_costs[idx]:,.2f}")
            else:
                print("  All startup costs are zero")
        
        if has_shutdown:
            shutdown_costs = network.generators['shut_down_cost']
            non_zero_shutdown = shutdown_costs[shutdown_costs > 0]
            print(f"\nShutdown costs:")
            print(f"  Total generators: {len(shutdown_costs)}")
            print(f"  Non-zero shutdown costs: {len(non_zero_shutdown)}")
            if len(non_zero_shutdown) > 0:
                print(f"  Min: ${shutdown_costs.min():,.2f}")
                print(f"  Max: ${shutdown_costs.max():,.2f}")
                print(f"  Mean: ${shutdown_costs.mean():,.2f}")
                print(f"  Sum: ${shutdown_costs.sum():,.2f}")
                print(f"\n  Sample generators with shutdown costs:")
                for idx in non_zero_shutdown.head(10).index:
                    print(f"    {idx}: ${shutdown_costs[idx]:,.2f}")
            else:
                print("  All shutdown costs are zero")
        
        # Check marginal costs
        if 'marginal_cost' in network.generators.columns:
            marginal_costs = network.generators['marginal_cost']
            print(f"\nMarginal costs:")
            print(f"  Min: ${marginal_costs.min():,.2f}/MWh")
            print(f"  Max: ${marginal_costs.max():,.2f}/MWh")
            print(f"  Mean: ${marginal_costs.mean():,.2f}/MWh")
    
    # Check storage units
    if hasattr(network, 'storage_units') and not network.storage_units.empty:
        print(f"\n\nStorage Units ({len(network.storage_units)}):")
        print("-" * 80)
        if 'marginal_cost' in network.storage_units.columns:
            marginal_costs = network.storage_units['marginal_cost']
            print(f"Marginal costs:")
            print(f"  Min: ${marginal_costs.min():,.2f}/MWh")
            print(f"  Max: ${marginal_costs.max():,.2f}/MWh")
            print(f"  Mean: ${marginal_costs.mean():,.2f}/MWh")


def inspect_psy_costs(psy_system):
    """Inspect cost data in PowerSystems system."""
    print("\n\n" + "=" * 80)
    print("POWERSYSTEMS SYSTEM COSTS")
    print("=" * 80)
    
    from r2x.models import ThermalStandard
    
    thermal_gens = list(psy_system.get_components(ThermalStandard))
    print(f"\nThermal Generators ({len(thermal_gens)}):")
    print("-" * 80)
    
    startup_costs = []
    shutdown_costs = []
    has_vom = []
    
    for gen in thermal_gens:
        op_cost = gen.operation_cost
        if op_cost is not None:
            # Get startup cost
            if hasattr(op_cost, 'start_up'):
                startup_val = op_cost.start_up
                if isinstance(startup_val, (int, float)):
                    startup_costs.append(startup_val)
                else:
                    # Could be StartUpStages tuple
                    startup_costs.append(max(startup_val) if hasattr(startup_val, '__iter__') else 0.0)
            
            # Get shutdown cost
            if hasattr(op_cost, 'shut_down'):
                shutdown_costs.append(op_cost.shut_down)
            
            # Check for VOM in variable cost
            if hasattr(op_cost, 'variable'):
                var_cost = op_cost.variable
                if hasattr(var_cost, 'vom_cost'):
                    vom_curve = var_cost.vom_cost
                    if hasattr(vom_curve, 'proportional_term'):
                        vom_val = vom_curve.proportional_term
                        has_vom.append(vom_val)
                    else:
                        has_vom.append(0.0)
                else:
                    has_vom.append(0.0)
    
    if startup_costs:
        startup_costs = [x for x in startup_costs if x is not None]
        non_zero_startup = [x for x in startup_costs if x > 0]
        print(f"\nStartup costs:")
        print(f"  Total generators: {len(startup_costs)}")
        print(f"  Non-zero startup costs: {len(non_zero_startup)}")
        if len(non_zero_startup) > 0:
            print(f"  Min: ${min(startup_costs):,.2f}")
            print(f"  Max: ${max(startup_costs):,.2f}")
            print(f"  Mean: ${sum(startup_costs)/len(startup_costs):,.2f}")
            print(f"  Sum: ${sum(startup_costs):,.2f}")
        else:
            print("  All startup costs are zero")
    
    if shutdown_costs:
        shutdown_costs = [x for x in shutdown_costs if x is not None]
        non_zero_shutdown = [x for x in shutdown_costs if x > 0]
        print(f"\nShutdown costs:")
        print(f"  Total generators: {len(shutdown_costs)}")
        print(f"  Non-zero shutdown costs: {len(non_zero_shutdown)}")
        if len(non_zero_shutdown) > 0:
            print(f"  Min: ${min(shutdown_costs):,.2f}")
            print(f"  Max: ${max(shutdown_costs):,.2f}")
            print(f"  Mean: ${sum(shutdown_costs)/len(shutdown_costs):,.2f}")
            print(f"  Sum: ${sum(shutdown_costs):,.2f}")
        else:
            print("  All shutdown costs are zero")
    
    if has_vom:
        non_zero_vom = [x for x in has_vom if x > 0]
        print(f"\nVOM costs:")
        print(f"  Total generators: {len(has_vom)}")
        print(f"  Non-zero VOM costs: {len(non_zero_vom)}")
        if len(non_zero_vom) > 0:
            print(f"  Min: ${min(has_vom):,.2f}/MW")
            print(f"  Max: ${max(has_vom):,.2f}/MW")
            print(f"  Mean: ${sum(has_vom)/len(has_vom):,.2f}/MW")
        else:
            print("  All VOM costs are zero")


if __name__ == "__main__":
    # Load PyPSA network
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    network = pypsa.Network(test_file)
    
    # Inspect PyPSA costs
    inspect_pypsa_costs(network)
    
    # Convert to PowerSystems
    parser = PypsaParser(network=network)
    pypsa_system = parser.build_system()
    
    mapping = create_default_mapping()
    
    psy_system = System(
        name="PSY system",
        auto_add_composed_components=True,
        time_series_storage_type=TimeSeriesStorageType.HDF5
    )
    
    # Convert components
    for component in pypsa_system._component_mgr.iter_all():
        try:
            pypsa_component_to_psy(component, pypsa_system, psy_system, mapping)
        except Exception as e:
            print(f"Warning: Failed to convert {component.name}: {e}")
            continue
    
    # Inspect PowerSystems costs
    inspect_psy_costs(psy_system)

