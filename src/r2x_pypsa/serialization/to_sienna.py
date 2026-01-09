"""Serialize system to sienna."""

import uuid
from pathlib import Path
from typing import Any, Dict

import orjson
from infrasys.component import Component
from infrasys.models import InfraSysBaseModel
from infrasys.value_curves import InputOutputCurve
from loguru import logger
from pint import Quantity
from r2x.api import System
from r2x.enums import ReserveDirection
from r2x.models import (
    Arc,
    Complex,
    FromTo_ToFrom,
    InputOutput,
    MinMax,
    UpDown,
)
from r2x.models.costs import OperationalCost

PARAMETRIZED_TYPES = {
    "ReserveDown": {"direction": ReserveDirection.DOWN},
    "ReserveUp": {"direction": ReserveDirection.UP},
}
PARAMETRIZED_FIELDS = {"direction"}


def get_parametrized_type(field: str, value: Any) -> str | None:
    for key, values in PARAMETRIZED_TYPES.items():
        if values.get(field) == value:
            return key
    return None


NODAL_TIME_SERIES_ATTRIBUTE = "zonal_to_nodal"
PARAMETRIZED_OUTPUT_TYPES = {"value_curve", "function_data", "loss"}
OUTPUT_METADATA = {"__metadata__", "internal"}
POWERSYSTEMS_PARAMETRIZED = {
    "RenewableGenerationCosts",
    "ThermalGenerationCosts",
    "StorageCosts",
    "HydroGenerationCost",
}

OUTPUT_FIELDS = {
    "HydroDispatch": [
        "name",
        "available",
        "bus",
        "active_power",
        "reactive_power",
        "rating",
        "prime_mover_type",
        "active_power_limits",
        "reactive_power_limits",
        "ramp_limits",
        "time_limits",
        "base_power",
        "operation_cost",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "PowerLoad": [
        "name",
        "available",
        "bus",
        "active_power",
        "reactive_power",
        "base_power",
        "max_reactive_power",
        "max_active_power",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "ACBus": [
        "name",
        "available",
        "number",
        "bustype",
        "magnitude",
        "voltage_limits",
        "area",
        "angle",
        "base_voltage",
        "load_zone",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "AreaInterchange": [
        "name",
        "available",
        "bus",
        "flow_limits",
        "active_power_flow",
        "from_area",
        "to_area",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "Area": [
        "name",
        "available",
        "peak_active_power",
        "peak_reactive_power",
        "load_response",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "ThermalStandard": [
        "name",
        "available",
        "bus",
        "active_power",
        "reactive_power",
        "rating",
        "base_power",
        "prime_mover_type",
        "active_power_limits",
        "reactive_power_limits",
        "ramp_limits",
        "time_limits",
        "storage_capacity",
        "operation_cost",
        "status",
        "time_at_status",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "HydroPumpedStorage": [
        "name",
        "available",
        "bus",
        "active_power",
        "reactive_power",
        "rating",
        "base_power",
        "prime_mover_type",
        "active_power_limits",
        "reactive_power_limits",
        "ramp_limits",
        "time_limits",
        "rating_pump",
        "active_power_limits_pump",
        "reactive_power_limits_pump",
        "ramp_limits_pump",
        "time_limits_pump",
        "storage_capacity",
        "inflow",
        "outflow",
        "initial_storage",
        "storage_target",
        "operation_cost",
        "pump_efficiency",
        "conversion_factor",
        "status",
        "time_at_status",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "RenewableDispatch": [
        "name",
        "available",
        "bus",
        "active_power",
        "active_power_limits",
        "reactive_power",
        "reactive_power_limits",
        "rating",
        "prime_mover_type",
        "power_factor",
        "operation_cost",
        "base_power",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "RenewableNonDispatch": [
        "name",
        "available",
        "bus",
        "active_power",
        "reactive_power",
        "rating",
        "prime_mover_type",
        "power_factor",
        "base_power",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "HydroEnergyReservoir": [
        "name",
        "available",
        "bus",
        "active_power",
        "reactive_power",
        "rating",
        "prime_mover_type",
        "active_power_limits",
        "reactive_power_limits",
        "ramp_limits",
        "time_limits",
        "base_power",
        "storage_capacity",
        "inflow",
        "initial_storage",
        "operation_cost",
        "storage_target",
        "conversion_factor",
        "status",
        "time_at_status",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
    "EnergyReservoirStorage": [
        "name",
        "available",
        "bus",
        "active_power",
        "reactive_power",
        "rating",
        "prime_mover_type",
        "active_power_limits",
        "reactive_power_limits",
        "ramp_limits",
        "time_limits",
        "base_power",
        "storage_capacity",
        "initial_storage_capacity_level",
        "efficiency",
        "input_active_power_limits",
        "output_active_power_limits",
        "discharge_efficiency",
        "storage_technology_type",
        "operation_cost",
        "storage_target",
        "services",
        "dynamic_injector",
        "ext",
        "internal",
    ],
}


def serialize_component_to_psy(
    component: Component, include: list[str] | None = None, *args, **kwargs
):
    """Serialize an infrasys to a valid PSY JSON format."""
    refs = {}
    include = OUTPUT_FIELDS.get(component.__class__.__name__)

    for field in type(component).model_fields:
        value = psy_serialization(component, field, *args, **kwargs)
        if value is not None:
            refs[field] = value
    
    data = component.model_dump(
        *args, mode="json", by_alias=True, round_trip=True, **kwargs
    )
    
    # Handle storage_target for EnergyReservoirStorage (stored in ext dict, not a model field)
    # Only include it if it exists in ext and is non-zero (indicating we want to use energy_target=true)
    # NOTE: We're NOT setting storage_target in ext anymore to avoid PowerSimulations bugs,
    # so this code path should rarely execute. If it does, only include it if non-zero.
    if component.__class__.__name__ == "EnergyReservoirStorage":
        storage_target_value = component.ext.get("storage_target")
        if storage_target_value is not None and storage_target_value != 0.0:
            data["storage_target"] = storage_target_value
            # Remove from ext dict to avoid duplication (it will be in ext from model_dump)
            if "ext" in data and isinstance(data["ext"], dict):
                data["ext"].pop("storage_target", None)
        # If storage_target is 0.0 or None, don't include it in the JSON at all
        # This prevents PowerSimulations from trying to read it when energy_target=false
    
    data = _ingest_psy_metadata(component, data)
    data.update(refs)

    if not include:
        include = []

    if not data:
        # breakpoint()
        return None

    # Python problems
    if isinstance(component, Arc):
        data["from"] = data.pop("from_to")
        data["to"] = data.pop("to_from")
    if "flow_limits" in data:
        data["flow_limits"] = {
            "from_to": data["flow_limits"]["from"],
            "to_from": data["flow_limits"]["to"],
        }

    return data


def _ingest_psy_metadata(component: Component, data: dict[str, Any], *args, **kwargs):
    """Serialize an infrasys object to a dictionary."""
    cls = type(component)
    data["__metadata__"] = {"module": "PowerSystems", "type": cls.__name__}
    if isinstance(component, Component):
        data["internal"] = {
            "uuid": {"value": data.pop("uuid")},
            "ext": None,
            "unit_info": None,
        }
    building_with_parameters = None
    for parametrized_field in component.model_fields_set & PARAMETRIZED_FIELDS:
        building_with_parameters = True
        parameter = get_parametrized_type(
            parametrized_field, getattr(component, parametrized_field)
        )
        data["__metadata__"]["parameters"] = [parameter]
    if building_with_parameters:
        data["__metadata__"]["construct_with_parameters"] = True
    return data


def psy_serialization(component, field):
    """Handle different objects type to createa compatible PSY object."""
    value = getattr(component, field)

    # If it is an Operational Cost we need to recurse the fields.
    if isinstance(value, Quantity):
        value = float(value.magnitude)
    elif isinstance(value, MinMax):
        value = {"min": value.min, "max": value.max}
    elif isinstance(value, FromTo_ToFrom):
        value = {"from": value.from_to, "to": value.to_from}
    elif isinstance(value, UpDown):
        value = {"up": value.up, "down": value.down}
    elif isinstance(value, InputOutput):
        value = {"in": value.input, "out": value.output}
    elif isinstance(value, Complex):
        value = {"real": value.real, "imag": value.imag}
    elif isinstance(value, OperationalCost | InputOutputCurve):
        value = _psy_parametric_serialization(value)
    elif isinstance(value, Component):
        value = _serialize_nested_component(value)
    elif isinstance(value, float | int):
        return value
    elif isinstance(value, list):
        value = [
            _serialize_nested_component(comp)
            for comp in value
            if isinstance(comp, Component)
        ]
    else:
        value = None

    return value


def _psy_parametric_serialization(component):
    def _serialize(obj):
        output_dict = {}
        parametric_types = set()  # Track parameterized types for this object

        for key in obj.model_fields_set:
            attribute = getattr(obj, key)

            if isinstance(attribute, Quantity):
                output_dict[key] = attribute.magnitude

            elif isinstance(attribute, InfraSysBaseModel):
                if key in PARAMETRIZED_OUTPUT_TYPES:
                    parametric_types.add(attribute.__class__.__name__)

                nested_output = _serialize(attribute)

                if "__metadata__" not in nested_output:
                    nested_output["__metadata__"] = {
                        "module": "InfrastructureSystems",
                        "type": attribute.__class__.__name__,
                    }

                output_dict[key] = nested_output
            else:
                output_dict[key] = attribute

        metadata = {
            "module": "InfrastructureSystems"
            if not isinstance(obj, OperationalCost)
            else "PowerSystems",
            "type": obj.__class__.__name__,
        }

        # Only add "parameters" if this object is in PARAMETRIZED_OUTPUT_TYPES
        if parametric_types:
            metadata["parameters"] = list(parametric_types)

        output_dict["__metadata__"] = metadata  # Ensure metadata is always included

        return output_dict

    return _serialize(component)


def _serialize_nested_component(component):
    """Return a JSON compatible component reference."""
    return {"value": str(component.uuid)}


def infrasys_to_psy(
    system: System,
    /,
    *,
    filename: Path | str,
    indent=None,
    **kwargs,
):
    """Serialize system to PSY."""
    logger.info("Serializing Sienna system to {}", filename)
    if not isinstance(filename, Path):
        filename = Path(filename)

    # Use matching filename for time series storage (e.g., elec_s380...json -> elec_s380...h5)
    # This prevents conflicts when multiple systems are in the same directory
    time_series_storage_file = filename.parent / f"{filename.stem}.h5"
    
    # Default filename that infrasys might have created
    default_storage_file = filename.parent / "time_series_storage.h5"
    time_series_metadata_file = filename.parent / "time_series_storage_metadata.db"

    # Close and remove HDF5 file if it exists (must be done before serialization)
    # This prevents "destination object already exists" errors
    if hasattr(system._time_series_mgr.storage, '_file') and system._time_series_mgr.storage._file is not None:
        try:
            system._time_series_mgr.storage._file.close()
        except Exception:
            pass
    
    # Remove both the default file and the new matching filename if they exist
    if default_storage_file.exists():
        default_storage_file.unlink()
        logger.debug(f"Removed default storage file: {default_storage_file}")
    
    if time_series_storage_file.exists():
        time_series_storage_file.unlink()
        logger.debug(f"Removed existing storage file: {time_series_storage_file}")
    
    if time_series_metadata_file.exists():
        time_series_metadata_file.unlink()
    
    # Update the storage file path in the system to match our desired filename
    # This ensures serialize() writes to the correct file
    # Try multiple possible attribute names that infrasys might use
    storage = system._time_series_mgr.storage
    if hasattr(storage, '_file_path'):
        storage._file_path = str(time_series_storage_file)
        logger.info(f"Updated storage._file_path to: {time_series_storage_file}")
    if hasattr(storage, 'file_path'):
        storage.file_path = str(time_series_storage_file)
        logger.info(f"Updated storage.file_path to: {time_series_storage_file}")
    if hasattr(storage, '_filename'):
        storage._filename = str(time_series_storage_file)
        logger.info(f"Updated storage._filename to: {time_series_storage_file}")
    if hasattr(storage, 'filename'):
        storage.filename = str(time_series_storage_file)
        logger.info(f"Updated storage.filename to: {time_series_storage_file}")
    
    # Log what the storage is actually using
    logger.info(f"Time series storage file will be: {time_series_storage_file}")
    logger.debug(f"Storage object attributes: {[attr for attr in dir(storage) if 'file' in attr.lower() or 'path' in attr.lower()]}")

    output_json: Dict[str, Any] = {
        "units_settings": {
            "base_value": 100.0,
            "unit_system": "SYSTEM_BASE",
            "__metadata__": {
                "module": "InfrastructureSystems",
                "type": "SystemUnitsSettings",
            },
        },
        "internal": {
            "uuid": {"value": str(uuid.uuid4())},
            "ext": None,
            "units_info": None,
        },
        "frequency": 60.0,
        "runchecks": True,
        "metadata": {
            "name": None,
            "description": None,
            "__metadata__": {"module": "PowerSystems", "type": "SystemMetadata"},
        },
        "data_format_version": "5.0.0",
        "data": {
            "time_series_storage_type": "InfrastructureSystems.Hdf5TimeSeriesStorage",
            "time_series_storage_file": str(time_series_storage_file.name),
            "masked_components": [],
            "supplemental_attribute_manager": {"attributes": [], "associations": []},
            "subsystems": {},
            "internal": {
                "uuid": {"value": str(uuid.uuid4())},
                "ext": {},
                "units_info": None,
            },
        },
    }
    components = [
        serialize_component_to_psy(
            component,
        )
        for component in system._component_mgr.iter_all()
    ]
    components = [component for component in components if component is not None]
    output_json["data"]["components"] = components

    dumped_data = orjson.dumps(output_json)
    with open(filename, "wb") as f:
        f.write(dumped_data)

    # Set scaling_factor_multiplier for time series
    # Time series are stored in per-unit (0-1), where 1.0 represents max capacity/load
    # PowerSimulations multiplies time series values by scaling_factor_multiplier to get MW
    # For ALL components (generators, storage, and loads): use get_max_active_power
    # This matches r2x-plexos behavior and ensures correct scaling in PowerSimulations
    scaling_factor_max = orjson.dumps(
        {"__metadata__": {"function": "get_max_active_power", "module": "PowerSystems"}}
    ).decode()

    with system._time_series_mgr._metadata_store._con as conn:
        conn.execute(
            """
            UPDATE time_series_associations
            SET scaling_factor_multiplier = IFNULL(scaling_factor_multiplier, '') || ?
            WHERE owner_type IN ('ThermalStandard', 'RenewableDispatch', 'EnergyReservoirStorage', 'PowerLoad')
            """,
            (scaling_factor_max,),
        )
    conn.commit()

    system._time_series_mgr.storage._serialize_compression_settings()
    
    # Serialize time series - this writes the HDF5 file and metadata
    # If the file already exists with objects, we need to ensure it's clean
    try:
        system._time_series_mgr.serialize(
            {}, filename.parent, "time_series_storage_metadata.db"
        )
    except RuntimeError as e:
        if "already exists" in str(e) or "Unable to synchronously copy object" in str(e):
            # If objects already exist, remove both files and try again
            logger.warning(f"HDF5 file had existing objects, removing and retrying: {e}")
            if default_storage_file.exists():
                default_storage_file.unlink()
            if time_series_storage_file.exists():
                time_series_storage_file.unlink()
            system._time_series_mgr.serialize(
                {}, filename.parent, "time_series_storage_metadata.db"
            )
        else:
            raise
    
    # After serialization, check if the file was created with the wrong name
    # and rename it to match our desired filename
    if default_storage_file.exists() and not time_series_storage_file.exists():
        logger.info(f"Renaming {default_storage_file} to {time_series_storage_file}")
        default_storage_file.rename(time_series_storage_file)
    elif default_storage_file.exists() and time_series_storage_file.exists():
        # Both exist - remove the default one
        logger.info(f"Removing duplicate default file: {default_storage_file}")
        default_storage_file.unlink()
    
    # Verify the correct file exists and update version if needed
    if not time_series_storage_file.exists():
        logger.warning(f"Expected HDF5 file {time_series_storage_file} was not created!")
        # Check what files were actually created
        h5_files = list(filename.parent.glob("*.h5"))
        logger.warning(f"Found HDF5 files in {filename.parent}: {h5_files}")
    else:
        # Ensure the file has the correct data format version
        import h5py
        try:
            with h5py.File(time_series_storage_file, "r+") as f:
                if "time_series" in f:
                    f["time_series"].attrs["data_format_version"] = "2.0.0"
                    # Add compression attributes required by newer InfrastructureSystems.jl
                    f["time_series"].attrs["compression_enabled"] = False
                    f["time_series"].attrs["compression_type"] = "DEFLATE"
                    f["time_series"].attrs["compression_level"] = 3
                    f["time_series"].attrs["compression_shuffle"] = True
        except Exception:
            pass  # If we can't update it, that's okay
        logger.info(f"✓ HDF5 file created successfully: {time_series_storage_file}")

    return
