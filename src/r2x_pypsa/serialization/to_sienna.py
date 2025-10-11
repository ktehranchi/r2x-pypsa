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
    data = _ingest_psy_metadata(component, data)
    data.update(refs)

    if not include:
        include = []

    if not data:
        breakpoint()
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

    time_series_storage_file = filename.parent / "time_series_storage.h5"

    if time_series_storage_file.exists():
        time_series_storage_file.unlink()

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
        "data_format_version": "4.0.0",
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

    scaling_factor = orjson.dumps(
        {"__metadata__": {"function": "get_max_active_power", "module": "PowerSystems"}}
    ).decode()

    with system._time_series_mgr._metadata_store._con as conn:
        conn.execute(
            """
            UPDATE time_series_associations
            SET scaling_factor_multiplier = IFNULL(scaling_factor_multiplier, '') || ?
            """,
            (scaling_factor,),
        )
    conn.commit()

    system._time_series_mgr.storage._serialize_compression_settings()
    system._time_series_mgr.serialize(
        {}, filename.parent, "time_series_storage_metadata.db"
    )

    return
