#!/usr/bin/env python3
"""Compare marginal costs between PyPSA network and PowerSystems system."""

import pypsa
from pathlib import Path
from r2x.api import System
from infrasys import TimeSeriesStorageType
from r2x_pypsa.parser import PypsaParser
from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
from r2x_pypsa.serialization import create_default_mapping
from r2x_pypsa.serialization.utils import get_pypsa_property
import pandas as pd

def compare_marginal_costs():
    """Compare marginal costs between PyPSA and PowerSystems."""
    # Load PyPSA network
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    network = pypsa.Network(test_file)
    
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
            continue
    
    print("=" * 80)
    print("MARGINAL COST COMPARISON")
    print("=" * 80)
    
    # Compare generators
    print("\nGENERATORS:")
    print("-" * 80)
    
    pypsa_costs = {}
    psy_costs = {}
    
    # Get PyPSA generator costs
    if hasattr(network, 'generators') and not network.generators.empty:
        for gen_name in network.generators.index:
            gen = network.generators.loc[gen_name]
            mc = gen.get('marginal_cost', 0.0)
            if pd.isna(mc):
                mc = 0.0
            pypsa_costs[gen_name] = float(mc)
    
    # Get PowerSystems generator costs
    from r2x.models import ThermalStandard, RenewableDispatch
    
    # Also check what get_pypsa_property returns for these generators
    debug_gens = []
    
    for gen in psy_system.get_components(ThermalStandard):
        gen_name = gen.name
        op_cost = gen.operation_cost
        
        # Extract cost first
        if op_cost is not None and hasattr(op_cost, 'variable'):
            var_cost = op_cost.variable
            if hasattr(var_cost, 'value_curve'):
                value_curve = var_cost.value_curve
                # Try different ways to access proportional_term
                mc = None
                if hasattr(value_curve, 'proportional_term'):
                    mc = value_curve.proportional_term
                elif hasattr(value_curve, 'get_proportional_term'):
                    mc = value_curve.get_proportional_term()
                elif hasattr(value_curve, 'function_data') and hasattr(value_curve.function_data, 'proportional_term'):
                    mc = value_curve.function_data.proportional_term
                elif hasattr(value_curve, '__dict__'):
                    # Try to inspect the object
                    d = value_curve.__dict__
                    if 'proportional_term' in d:
                        mc = d['proportional_term']
                    elif 'function_data' in d and hasattr(d['function_data'], 'proportional_term'):
                        mc = d['function_data'].proportional_term
                
                psy_costs[gen_name] = float(mc) if mc is not None else 0.0
            else:
                psy_costs[gen_name] = 0.0
        else:
            psy_costs[gen_name] = 0.0
        
        # Debug: check what get_pypsa_property would return
        if gen_name in pypsa_costs and pypsa_costs[gen_name] > 0:
            # Find the corresponding PyPSA component
            for comp in pypsa_system._component_mgr.iter_all():
                if hasattr(comp, 'name') and comp.name == gen_name:
                    mc_prop = get_pypsa_property(pypsa_system, comp, "marginal_cost")
                    # Also check what create_operational_cost would return
                    from r2x_pypsa.serialization.cost_models import create_operational_cost
                    test_cost = create_operational_cost(gen, comp, pypsa_system)
                    debug_gens.append({
                        'name': gen_name,
                        'pypsa_network': pypsa_costs[gen_name],
                        'get_pypsa_property': mc_prop,
                        'create_operational_cost': test_cost is not None,
                        'op_cost_is_none': op_cost is None,
                        'psy_cost': psy_costs[gen_name],
                    })
                    break
    
    for gen in psy_system.get_components(RenewableDispatch):
        gen_name = gen.name
        op_cost = gen.operation_cost
        if op_cost is not None and hasattr(op_cost, 'variable'):
            var_cost = op_cost.variable
            if hasattr(var_cost, 'value_curve'):
                value_curve = var_cost.value_curve
                if hasattr(value_curve, 'proportional_term'):
                    mc = value_curve.proportional_term
                    psy_costs[gen_name] = float(mc) if mc is not None else 0.0
                else:
                    psy_costs[gen_name] = 0.0
            else:
                psy_costs[gen_name] = 0.0
        else:
            psy_costs[gen_name] = 0.0
    
    # Find matching generators and compare
    matching_gens = set(pypsa_costs.keys()) & set(psy_costs.keys())
    
    print(f"\nTotal PyPSA generators: {len(pypsa_costs)}")
    print(f"Total PowerSystems generators: {len(psy_costs)}")
    print(f"Matching generators: {len(matching_gens)}")
    
    # Find differences
    differences = []
    negative_clipped = []
    zeroed_out = []
    
    for gen_name in sorted(matching_gens)[:50]:  # Check first 50
        pypsa_mc = pypsa_costs[gen_name]
        psy_mc = psy_costs[gen_name]
        
        if abs(pypsa_mc - psy_mc) > 1e-6:  # Significant difference
            differences.append({
                'name': gen_name,
                'pypsa': pypsa_mc,
                'psy': psy_mc,
                'diff': psy_mc - pypsa_mc,
            })
            
            # Check if negative was clipped
            if pypsa_mc < 0 and psy_mc == 0.0:
                negative_clipped.append({
                    'name': gen_name,
                    'pypsa': pypsa_mc,
                    'psy': psy_mc,
                })
            
            # Check if positive was zeroed
            if pypsa_mc > 0 and psy_mc == 0.0:
                zeroed_out.append({
                    'name': gen_name,
                    'pypsa': pypsa_mc,
                    'psy': psy_mc,
                })
    
    if debug_gens:
        print(f"\n🔍 DEBUG: Checking get_pypsa_property for {len(debug_gens)} generators:")
        df_debug = pd.DataFrame(debug_gens[:10])
        print(df_debug.to_string(index=False))
    
    if differences:
        print(f"\n⚠️  Found {len(differences)} generators with cost differences:")
        print("\nSample differences:")
        df = pd.DataFrame(differences[:20])
        print(df.to_string(index=False))
        
        if negative_clipped:
            print(f"\n⚠️  Found {len(negative_clipped)} generators with NEGATIVE marginal costs that were clipped to 0:")
            print("\nSample negative costs that were clipped:")
            df_neg = pd.DataFrame(negative_clipped[:10])
            print(df_neg.to_string(index=False))
            print(f"\nTotal impact: ${sum([x['pypsa'] for x in negative_clipped]):,.2f} (these would reduce costs)")
        
        if zeroed_out:
            print(f"\n⚠️  Found {len(zeroed_out)} generators with POSITIVE marginal costs that were zeroed:")
            print("\nSample positive costs that were zeroed:")
            df_zero = pd.DataFrame(zeroed_out[:10])
            print(df_zero.to_string(index=False))
    else:
        print("\n✓ All matching generators have the same marginal costs")
    
    # Summary statistics
    print("\n" + "-" * 80)
    print("SUMMARY STATISTICS:")
    print("-" * 80)
    
    pypsa_values = list(pypsa_costs.values())
    psy_values = list(psy_costs.values())
    
    print(f"\nPyPSA marginal costs:")
    print(f"  Count: {len(pypsa_values)}")
    print(f"  Min: ${min(pypsa_values):,.2f}/MWh")
    print(f"  Max: ${max(pypsa_values):,.2f}/MWh")
    print(f"  Mean: ${sum(pypsa_values)/len(pypsa_values):,.2f}/MWh")
    print(f"  Negative values: {sum(1 for x in pypsa_values if x < 0)}")
    print(f"  Zero values: {sum(1 for x in pypsa_values if x == 0)}")
    
    print(f"\nPowerSystems marginal costs:")
    print(f"  Count: {len(psy_values)}")
    print(f"  Min: ${min(psy_values):,.2f}/MWh")
    print(f"  Max: ${max(psy_values):,.2f}/MWh")
    print(f"  Mean: ${sum(psy_values)/len(psy_values):,.2f}/MWh")
    print(f"  Negative values: {sum(1 for x in psy_values if x < 0)}")
    print(f"  Zero values: {sum(1 for x in psy_values if x == 0)}")


if __name__ == "__main__":
    compare_marginal_costs()

