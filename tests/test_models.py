import pytest
import numpy as np
import pandas as pd
from r2x_pypsa.models import PypsaGenerator
from r2x_pypsa.models.property_values import PypsaProperty


def test_pypsa_generator():
    """Test PypsaGenerator model creation and properties."""
    
    generator = PypsaGenerator(
        name="test_gen",
        bus="bus1",
        carrier=PypsaProperty.create(value="solar"),
        p_nom=PypsaProperty.create(value=100.0, units="MW"),
        marginal_cost=PypsaProperty.create(value=25.0, units="usd/MWh")
    )
    
    assert isinstance(generator, PypsaGenerator)
    assert generator.name == "test_gen"
    assert generator.bus == "bus1"
    assert generator.carrier.get_value() == "solar"
    assert generator.p_nom.get_value() == 100.0
    assert generator.marginal_cost.get_value() == 25.0
    assert generator.uuid is not None


def test_pypsa_generator_defaults():
    """Test PypsaGenerator with default values."""
    
    generator = PypsaGenerator(
        name="test_gen",
        bus="bus1",
        carrier=PypsaProperty.create(value="solar")
    )
    
    assert generator.p_nom.get_value() == 0.0
    assert generator.p_nom_extendable.get_value() is False
    assert generator.marginal_cost.get_value() == 0.0
    assert generator.capital_cost.get_value() == 0.0
    assert generator.efficiency.get_value() == 1.0
    assert generator.p_max_pu.get_value() == 1.0
    assert generator.p_min_pu.get_value() == 0.0
    assert generator.uuid is not None


def test_pypsa_generator_negative_marginal_cost():
    """Test that generators can have negative marginal costs (e.g., for renewables with tax credits)."""
    
    # Wind generator with negative marginal cost due to PTC
    generator = PypsaGenerator(
        name="wind_with_ptc",
        bus="bus1",
        carrier=PypsaProperty.create(value="onwind"),
        p_nom=PypsaProperty.create(value=100.0, units="MW"),
        marginal_cost=PypsaProperty.create(value=-22.0, units="usd/MWh")  # Negative due to PTC
    )
    
    assert generator.marginal_cost.get_value() == -22.0
    assert generator.name == "wind_with_ptc"
    
    # Solar generator with negative marginal cost
    solar_gen = PypsaGenerator(
        name="solar_with_itc",
        bus="bus1",
        carrier=PypsaProperty.create(value="solar"),
        marginal_cost=PypsaProperty.create(value=-15.0, units="usd/MWh")
    )
    
    assert solar_gen.marginal_cost.get_value() == -15.0


def test_pypsa_generator_p_max_pu_static_vs_timeseries():
    """Test that p_max_pu static value is used for capacity, not time series max.
    
    This verifies the fix for the bug where renewable capacity was calculated
    using time series capacity factor instead of nameplate capacity.
    """
    import pandas as pd
    
    # Create a renewable generator with p_max_pu time series (capacity factor)
    # Static p_max_pu should be 1.0 (nameplate), time series is capacity factor (0-1)
    capacity_factor_ts = pd.Series([0.2, 0.3, 0.25, 0.4], index=pd.date_range("2023-01-01", periods=4, freq="h"))
    
    generator = PypsaGenerator(
        name="solar_gen",
        bus="bus1",
        carrier=PypsaProperty.create(value="solar"),
        p_nom=PypsaProperty.create(value=100.0, units="MW"),
        p_max_pu=PypsaProperty.create(value=1.0, time_series=capacity_factor_ts)  # Static = 1.0, TS = capacity factor
    )
    
    # Verify static value is 1.0 (nameplate)
    assert generator.p_max_pu.value == 1.0
    
    # Verify time series exists and has capacity factor values
    assert generator.p_max_pu.has_time_series()
    assert generator.p_max_pu.time_series.max() == 0.4  # Peak capacity factor
    
    # Verify get_value() returns static value, not time series max
    # (This is what should be used for active_power_limits.max)
    assert generator.p_max_pu.get_value() == 1.0  # Should return static value, not time series mean/max


def test_pypsa_generator_uuid_generation():
    """Test that UUID is auto-generated when not provided."""
    
    gen1 = PypsaGenerator(name="gen1", bus="bus1", carrier=PypsaProperty.create(value="solar"))
    gen2 = PypsaGenerator(name="gen2", bus="bus1", carrier=PypsaProperty.create(value="wind"))
    
    assert gen1.uuid != gen2.uuid
    assert str(gen1.uuid) != ""
    assert str(gen2.uuid) != ""


def test_solar_time_series_conversion():
    """Test that solar generator p_max_pu time series is correctly converted to PSY.
    
    This test matches the workflow in run_sienna_ed.jl:
    1. Verify base_power = p_nom (nameplate capacity in MW)
    2. Verify rating = 1.0 and power_factor = 1.0 (so get_max_active_power() = base_power)
    3. Verify time series is in per-unit (0-1) - capacity factors
    4. Verify available generation = capacity_factor * get_max_active_power() at each timestep
    """
    import pandas as pd
    import numpy as np
    from r2x.api import System
    from r2x.models import RenewableDispatch
    from r2x_pypsa.models import PypsaBus
    from r2x_pypsa.serialization.pypsa_to_psy import pypsa_component_to_psy
    from r2x_pypsa.serialization import create_default_mapping
    
    # Create a simple solar generator with time series (matching PyPSA format)
    p_nom = 100.0  # MW - nameplate capacity
    capacity_factor_ts = pd.Series(
        [0.0, 0.1, 0.5, 0.8, 1.0, 0.9, 0.6, 0.2],
        index=pd.date_range("2023-01-01", periods=8, freq="h")
    )
    
    pypsa_system = System(name="test")
    bus = PypsaBus(name="bus1")
    pypsa_system.add_component(bus)
    
    generator = PypsaGenerator(
        name="solar_1",
        bus="bus1",
        carrier=PypsaProperty.create(value="solar"),
        p_nom=PypsaProperty.create(value=p_nom, units="MW"),
        p_max_pu=PypsaProperty.create(value=1.0, time_series=capacity_factor_ts)  # Static=1.0, TS=capacity factors
    )
    pypsa_system.add_component(generator)
    
    # Convert to PSY
    mapping = create_default_mapping()
    psy_system = System(name="psy_test")
    
    pypsa_component_to_psy(bus, pypsa_system, psy_system, mapping)
    pypsa_component_to_psy(generator, pypsa_system, psy_system, mapping)
    
    # Check generator was converted to RenewableDispatch
    psy_gen = psy_system.get_component(RenewableDispatch, "solar_1")
    assert psy_gen is not None, "Should create RenewableDispatch"
    
    # Verify base_power = p_nom (nameplate capacity in MW)
    # This matches run_sienna_ed.jl line 957: base_power = get_base_power(gen)
    base_power_mw = psy_gen.base_power.magnitude if hasattr(psy_gen.base_power, 'magnitude') else psy_gen.base_power
    assert abs(base_power_mw - p_nom) < 1e-6, f"Base power should be {p_nom} MW, got {base_power_mw}"
    
    # Verify rating = 1.0 and power_factor = 1.0
    # This ensures get_max_active_power() = rating * power_factor * base_power = 1.0 * 1.0 * p_nom = p_nom
    # Matching run_sienna_ed.jl line 961: max_active_power = get_max_active_power(gen) should return p_nom
    rating = psy_gen.rating.magnitude if hasattr(psy_gen.rating, 'magnitude') else psy_gen.rating
    power_factor = psy_gen.power_factor
    assert abs(rating - 1.0) < 1e-6, f"Rating should be 1.0 (per-unit), got {rating}"
    assert abs(power_factor - 1.0) < 1e-6, f"Power factor should be 1.0, got {power_factor}"
    
    # Calculate get_max_active_power() = rating * power_factor * base_power
    # In Julia: get_max_active_power(gen) returns MW (with NATURAL_UNITS)
    max_active_power_mw = rating * power_factor * base_power_mw
    assert abs(max_active_power_mw - p_nom) < 1e-6, \
        f"get_max_active_power() should be {p_nom} MW, got {max_active_power_mw}"
    
    # Check time series exists and is named "max_active_power"
    time_series_list = list(psy_system.list_time_series(psy_gen))
    assert len(time_series_list) > 0, "Should have time series"
    
    max_power_ts = None
    for ts in time_series_list:
        if ts.name == "max_active_power":
            max_power_ts = ts
            break
    
    assert max_power_ts is not None, "Should have 'max_active_power' time series"
    
    # Verify time series is in per-unit (0-1) - capacity factors
    # Matching run_sienna_ed.jl line 562: capacity_factor = TimeSeries.values(ts_data)[step]
    # and line 970: ts_values = TimeSeries.values(ts_data) (in per-unit)
    ts_values = np.array(max_power_ts.data) if not isinstance(max_power_ts.data, np.ndarray) else max_power_ts.data
    assert len(ts_values) == len(capacity_factor_ts), "Time series length should match"
    
    # Verify values are in per-unit range (0-1)
    assert all(0.0 <= val <= 1.0 for val in ts_values), "Time series should be in per-unit range (0-1)"
    
    # Verify time series values match original capacity factors
    assert all(abs(ts_values[i] - capacity_factor_ts.values[i]) < 1e-6 for i in range(len(ts_values))), \
        "Time series values should match original capacity factors"
    
    # Verify available generation calculation (matching run_sienna_ed.jl line 564)
    # available = capacity_factor * max_cap
    # where max_cap = get_max_active_power() = p_nom
    for i, capacity_factor in enumerate(capacity_factor_ts.values):
        available_mw = capacity_factor * max_active_power_mw
        expected_mw = capacity_factor * p_nom
        assert abs(available_mw - expected_mw) < 1e-6, \
            f"Available generation at timestep {i} should be {expected_mw} MW, got {available_mw}"


def test_solar_capacity_factors_match():
    """Test that solar capacity factors match between PyPSA and Sienna."""
    import pypsa
    from pathlib import Path
    from r2x.api import System
    from test_helpers import get_sienna_capacity_factors
    
    # Load PyPSA network
    network = pypsa.Network("tests/data/elec_s380_c7a_ec_lv1.5_RPS-REM-TCT-1h_E.nc")
    
    # Load Sienna system
    test_dir = Path(__file__).parent
    sienna_json = test_dir / "test_output" / "elec_s380_c7a_ec_lv1_output_optimized.json"
    sienna_h5 = test_dir / "test_output" / "elec_s380_c7a_ec_lv1_output_optimized.h5"
    
    # Skip if files don't exist
    if not sienna_json.exists() or not sienna_h5.exists():
        pytest.skip("Sienna output files not found. Run test_end_to_end first.")
    
    sys = System(str(sienna_json))
    
    # Test a single specific generator
    test_generators = ["p600 0 solar existing"]
    test_times = pd.date_range("2030-01-01", periods=10, freq="h")
    
    for gen_name in test_generators:
        # Skip if generator doesn't exist in PyPSA
        if gen_name not in network.generators.index:
            continue
        if gen_name not in network.generators_t.p_max_pu.columns:
            continue
        
        # Get PyPSA capacity factors
        # Handle MultiIndex snapshots (period, timestamp) or simple DatetimeIndex
        pypsa_cf_series = network.generators_t.p_max_pu[gen_name]
        
        # If MultiIndex, extract the timestamp part
        if isinstance(pypsa_cf_series.index, pd.MultiIndex):
            # MultiIndex has (period, timestamp) - use the timestamp (second level)
            pypsa_cf_series = pypsa_cf_series.reset_index(level=0, drop=True)
        
        # Select the test times
        pypsa_cf = pypsa_cf_series.loc[test_times]
        
        # Get Sienna capacity factors (from JSON/H5)
        try:
            sienna_cf = get_sienna_capacity_factors(
                sienna_json,
                gen_name,
                test_times,
                h5_file=sienna_h5
            )
        except ValueError as e:
            pytest.skip(f"Could not load Sienna capacity factors for {gen_name}: {e}. "
                       f"This may indicate that time series metadata is not stored in JSON. "
                       f"Consider using System API directly.")
        
        # Align indices (handle potential time differences)
        if len(pypsa_cf) != len(sienna_cf) or not pypsa_cf.index.equals(sienna_cf.index):
            # Reindex to common times
            common_times = pypsa_cf.index.intersection(sienna_cf.index)
            if len(common_times) > 0:
                pypsa_cf = pypsa_cf.loc[common_times]
                sienna_cf = sienna_cf.loc[common_times]
            else:
                # Use nearest neighbor matching
                pypsa_cf = pypsa_cf.reindex(sienna_cf.index, method='nearest')
        
        # Compare
        assert len(pypsa_cf) > 0 and len(sienna_cf) > 0, \
            f"No matching timesteps for {gen_name}"
        
        assert np.allclose(pypsa_cf.values, sienna_cf.values, rtol=1e-6, atol=1e-6), \
            f"Capacity factors don't match for {gen_name}. " \
            f"Max diff: {np.abs(pypsa_cf.values - sienna_cf.values).max():.2e}, " \
            f"Mean diff: {np.abs(pypsa_cf.values - sienna_cf.values).mean():.2e}"
