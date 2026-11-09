"""JSON export / import for preset libraries."""

import json

from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import utils
from .properties import PRESET_FIELDS

SCHEMA_VERSION = 1

VECTOR_FIELDS = {"matrix_basis", "delta_matrix"}
BOOL_FIELDS = {"use_dof"}
STRING_FIELDS = {
    "name",
    "camera_name",
    "rotation_mode",
    "camera_type",
    "sensor_fit",
    "panorama_type",
    "focus_object_name",
}

ROTATION_IDS = {
    'XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX', 'QUATERNION', 'AXIS_ANGLE',
}
CAMERA_TYPE_IDS = {'PERSP', 'ORTHO', 'PANO'}
SENSOR_FIT_IDS = {'AUTO', 'HORIZONTAL', 'VERTICAL'}


def preset_to_dict(preset):
    data = {}
    for field in PRESET_FIELDS:
        value = getattr(preset, field)
        if field in VECTOR_FIELDS:
            data[field] = [float(item) for item in tuple(value)]
        elif field in BOOL_FIELDS:
            data[field] = bool(value)
        elif field in STRING_FIELDS:
            data[field] = str(value)
        else:
            data[field] = float(value)
    return data


def dict_to_preset(preset, data):
    """Fill a preset from a dict, silently skipping unusable values."""
    for field in PRESET_FIELDS:
        if field not in data:
            continue
        value = data[field]
        try:
            if field in VECTOR_FIELDS:
                vector = [float(item) for item in list(value)]
                if len(vector) != 16:
                    continue
                setattr(preset, field, vector)
            elif field in BOOL_FIELDS:
                setattr(preset, field, bool(value))
            elif field in STRING_FIELDS:
                text = str(value)
                if field == "rotation_mode" and text not in ROTATION_IDS:
                    continue
                if field == "camera_type" and text not in CAMERA_TYPE_IDS:
                    continue
                if field == "sensor_fit" and text not in SENSOR_FIT_IDS:
                    continue
                setattr(preset, field, text)
            else:
                setattr(preset, field, float(value))
        except (TypeError, ValueError):
            continue


class CAMPRESET_OT_export(Operator, ExportHelper):
    """Write every preset of the current scene to a JSON file"""

    bl_idname = "cam_preset.export"
    bl_label = "Export Presets"

    filename_ext = ".json"

    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context):
        if getattr(context, "scene", None) is None:
            return False
        return len(context.scene.cam_presets) > 0

    def execute(self, context):
        presets = context.scene.cam_presets
        payload = {
            "schema": SCHEMA_VERSION,
            "presets": [preset_to_dict(preset) for preset in presets],
        }
        try:
            with open(self.filepath, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError as error:
            self.report({'ERROR'}, "Could not write file: {}".format(error))
            return {'CANCELLED'}

        self.report(
            {'INFO'}, "Exported {} preset(s) to {}".format(len(presets), self.filepath)
        )
        return {'FINISHED'}


class CAMPRESET_OT_load(Operator, ImportHelper):
    """Append presets from a JSON file to the current scene"""

    bl_idname = "cam_preset.load"
    bl_label = "Load Presets"

    filename_ext = ".json"

    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context):
        return getattr(context, "scene", None) is not None

    def execute(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except OSError as error:
            self.report({'ERROR'}, "Could not read file: {}".format(error))
            return {'CANCELLED'}
        except ValueError as error:
            self.report({'ERROR'}, "Invalid JSON: {}".format(error))
            return {'CANCELLED'}

        entries = payload.get("presets") if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            self.report({'ERROR'}, "File does not contain a preset list")
            return {'CANCELLED'}

        scene = context.scene
        presets = scene.cam_presets
        added = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            preset = presets.add()
            dict_to_preset(preset, entry)
            preset.name = utils.unique_name(
                presets, preset.name or "Preset", exclude=preset
            )
            added += 1

        if added:
            scene.cam_presets_index = len(presets) - 1
            self.report({'INFO'}, "Imported {} preset(s)".format(added))
        else:
            self.report({'WARNING'}, "No presets found in the file")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (CAMPRESET_OT_export, CAMPRESET_OT_load)
