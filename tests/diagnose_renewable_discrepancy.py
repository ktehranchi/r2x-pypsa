"""Diagnostic script to identify why PyPSA has more renewables than Sienna.

This script compares renewable generators between PyPSA and Sienna to find:
1. Generators that exist in PyPSA but not in Sienna
2. Capacity differences
3. Time series differences
4. Dispatch differences
"""

import pypsa
import pandas as pd
import json
import h5py
import sqlite3
from pathlib import Path
from loguru import logger

def diagnose_renewable_discrepancy():
    """Diagnose why PyPSA has more renewables than Sienna."""
    
    # Paths
    test_file = Path("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    json_file = Path("tests/test_output/elec_s380_c7a_ec_lv1_comparison.json")
    h5_file = Path("tests/test_output/elec_s380_c7a_ec_lv1_comparison.h5")
    pypsa_dispatch_file = Path("tests/test_output/pypsa_dispatch.csv")
    sienna_dispatch_file = Path("tests/test_output/sienna_dispatch.csv")
    
    logger.info("=" * 80)
    logger.info("RENEWABLE DISCREPANCY DIAGNOSIS")
    logger.info("=" * 80)
    
    # Load PyPSA network
    network = pypsa.Network(test_file)
    
    # Apply same modifications as in test
    for component in network.components.keys():
        for attr in ["p_nom_extendable", "s_nom_extendable", "e_nom_extendable"]:
            if attr in network.df(component).columns:
                network.df(component)[attr] = False
    
    network.loads_t.p_set *= 0.75
    
    # Get PyPSA renewable generators
    renewable_carriers = ['solar', 'onwind', 'offwind', 'offwind_floating', 'wind', 'hydro', 'ror']
    pypsa_renewables = network.generators[
        (network.generators.carrier.isin(renewable_carriers)) & 
        (network.generators.p_nom > 0)
    ].copy()
    
    logger.info(f"\nPyPSA Renewable Generators: {len(pypsa_renewables)}")
    logger.info(f"Total PyPSA renewable capacity: {pypsa_renewables.p_nom.sum():.2f} MW")
    
    # Check which generators have time series
    pypsa_with_ts = []
    pypsa_without_ts = []
    
    if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_max_pu'):
        for gen_name in pypsa_renewables.index:
            if gen_name in network.generators_t.p_max_pu.columns:
                pypsa_with_ts.append(gen_name)
            else:
                pypsa_without_ts.append(gen_name)
    else:
        pypsa_without_ts = list(pypsa_renewables.index)
    
    logger.info(f"  Generators with p_max_pu time series: {len(pypsa_with_ts)}")
    logger.info(f"  Generators without p_max_pu time series: {len(pypsa_without_ts)}")
    
    if pypsa_without_ts:
        logger.warning(f"  ⚠️  PyPSA generators without time series: {len(pypsa_without_ts)}")
        for gen_name in pypsa_without_ts[:10]:  # Show first 10
            gen = pypsa_renewables.loc[gen_name]
            logger.warning(f"    - {gen_name}: carrier={gen.carrier}, p_nom={gen.p_nom:.2f} MW")
    
    # Load Sienna data
    if not json_file.exists():
        logger.error(f"Sienna JSON file not found: {json_file}")
        return
    
    with open(json_file) as f:
        sienna_data = json.load(f)
    
    components = sienna_data.get('data', {}).get('components', [])
    
    # Get Sienna renewable generators
    sienna_renewables = [
        c for c in components
        if c.get('__metadata__', {}).get('type') == 'RenewableDispatch'
    ]
    
    logger.info(f"\nSienna Renewable Generators: {len(sienna_renewables)}")
    
    # Calculate Sienna capacity
    sienna_capacity = sum(
        g.get('rating', 0.0) * g.get('base_power', 0.0) * g.get('power_factor', 1.0)
        for g in sienna_renewables
    )
    logger.info(f"Total Sienna renewable capacity: {sienna_capacity:.2f} MW")
    
    # Check which Sienna generators have time series
    sienna_with_ts = []
    sienna_without_ts = []
    
    if h5_file.exists():
        with h5py.File(h5_file, 'r') as h5:
            if 'time_series_metadata' in h5:
                db_data = h5['time_series_metadata'][()]
                db_path = Path(".temp_metadata_diagnosis.db")
                
                with open(db_path, 'wb') as db_file:
                    db_file.write(bytes(db_data))
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                table_name = 'time_series_metadata' if 'time_series_metadata' in tables else 'time_series_associations'
                
                for gen in sienna_renewables:
                    gen_uuid = gen.get('internal', {}).get('uuid', {}).get('value')
                    if not gen_uuid:
                        sienna_without_ts.append(gen.get('name', 'unknown'))
                        continue
                    
                    query = f'''
                        SELECT COUNT(*)
                        FROM {table_name}
                        WHERE owner_uuid = ? AND owner_type = 'RenewableDispatch' AND name = 'max_active_power'
                    '''
                    cursor.execute(query, (gen_uuid,))
                    count = cursor.fetchone()[0]
                    
                    if count > 0:
                        sienna_with_ts.append(gen.get('name', 'unknown'))
                    else:
                        sienna_without_ts.append(gen.get('name', 'unknown'))
                
                conn.close()
                db_path.unlink()
            else:
                sienna_without_ts = [g.get('name', 'unknown') for g in sienna_renewables]
    else:
        sienna_without_ts = [g.get('name', 'unknown') for g in sienna_renewables]
    
    logger.info(f"  Generators with time series: {len(sienna_with_ts)}")
    logger.info(f"  Generators without time series: {len(sienna_without_ts)}")
    
    if sienna_without_ts:
        logger.warning(f"  ⚠️  Sienna generators without time series: {len(sienna_without_ts)}")
        for gen_name in sienna_without_ts[:10]:  # Show first 10
            gen = next((g for g in sienna_renewables if g.get('name') == gen_name), None)
            if gen:
                capacity = gen.get('rating', 0.0) * gen.get('base_power', 0.0) * gen.get('power_factor', 1.0)
                logger.warning(f"    - {gen_name}: capacity={capacity:.2f} MW")
    
    # Compare generator names
    pypsa_names = set(pypsa_renewables.index)
    sienna_names = set(g.get('name') for g in sienna_renewables)
    
    missing_in_sienna = pypsa_names - sienna_names
    extra_in_sienna = sienna_names - pypsa_names
    
    logger.info(f"\nGenerator Name Comparison:")
    logger.info(f"  PyPSA generators: {len(pypsa_names)}")
    logger.info(f"  Sienna generators: {len(sienna_names)}")
    logger.info(f"  Missing in Sienna: {len(missing_in_sienna)}")
    logger.info(f"  Extra in Sienna: {len(extra_in_sienna)}")
    
    if missing_in_sienna:
        logger.warning(f"\n⚠️  PyPSA generators missing in Sienna ({len(missing_in_sienna)}):")
        missing_capacity = 0.0
        for gen_name in sorted(missing_in_sienna)[:20]:  # Show first 20
            gen = pypsa_renewables.loc[gen_name]
            missing_capacity += gen.p_nom
            has_ts = "✓" if gen_name in pypsa_with_ts else "✗"
            logger.warning(f"    - {gen_name}: carrier={gen.carrier}, p_nom={gen.p_nom:.2f} MW, TS={has_ts}")
        if len(missing_in_sienna) > 20:
            logger.warning(f"    ... and {len(missing_in_sienna) - 20} more")
        logger.warning(f"  Total missing capacity: {missing_capacity:.2f} MW")
    
    if extra_in_sienna:
        logger.info(f"\nSienna generators not in PyPSA ({len(extra_in_sienna)}):")
        for gen_name in sorted(extra_in_sienna)[:10]:
            gen = next((g for g in sienna_renewables if g.get('name') == gen_name), None)
            if gen:
                capacity = gen.get('rating', 0.0) * gen.get('base_power', 0.0) * gen.get('power_factor', 1.0)
                logger.info(f"    - {gen_name}: capacity={capacity:.2f} MW")
    
    # Compare dispatch totals if files exist
    if pypsa_dispatch_file.exists() and sienna_dispatch_file.exists():
        logger.info(f"\n" + "=" * 80)
        logger.info("DISPATCH COMPARISON")
        logger.info("=" * 80)
        
        pypsa_df = pd.read_csv(pypsa_dispatch_file)
        sienna_df = pd.read_csv(sienna_dispatch_file)
        
        # Filter renewables
        pypsa_renewable_dispatch = pypsa_df[
            pypsa_df['carrier'].isin(renewable_carriers)
        ]
        
        # Map Sienna carriers to PyPSA names
        def map_sienna_to_pypsa(carrier):
            mapping = {
                'PVe': 'solar',
                'WT': 'onwind',
                'WS': 'offwind',
                'HY': 'hydro'
            }
            return mapping.get(carrier, carrier)
        
        sienna_df_mapped = sienna_df.copy()
        sienna_df_mapped['carrier'] = sienna_df_mapped['carrier'].apply(map_sienna_to_pypsa)
        sienna_renewable_dispatch = sienna_df_mapped[
            sienna_df_mapped['carrier'].isin(renewable_carriers)
        ]
        
        pypsa_total = pypsa_renewable_dispatch['value'].sum()
        sienna_total = sienna_renewable_dispatch['value'].sum()
        difference = pypsa_total - sienna_total
        
        logger.info(f"PyPSA renewable dispatch total: {pypsa_total:.2f} MWh")
        logger.info(f"Sienna renewable dispatch total: {sienna_total:.2f} MWh")
        logger.info(f"Difference: {difference:.2f} MWh (PyPSA has {difference:.2f} MWh more)")
        
        # Break down by carrier
        logger.info(f"\nBreakdown by carrier:")
        for carrier in renewable_carriers:
            pypsa_carrier = pypsa_renewable_dispatch[pypsa_renewable_dispatch['carrier'] == carrier]['value'].sum()
            sienna_carrier = sienna_renewable_dispatch[sienna_renewable_dispatch['carrier'] == carrier]['value'].sum()
            diff = pypsa_carrier - sienna_carrier
            if abs(pypsa_carrier) > 0.01 or abs(sienna_carrier) > 0.01:
                logger.info(f"  {carrier}:")
                logger.info(f"    PyPSA: {pypsa_carrier:.2f} MWh")
                logger.info(f"    Sienna: {sienna_carrier:.2f} MWh")
                logger.info(f"    Difference: {diff:.2f} MWh")
    
    logger.info("=" * 80)

if __name__ == "__main__":
    diagnose_renewable_discrepancy()

