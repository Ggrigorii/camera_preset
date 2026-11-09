"""JSON export / import for preset libraries."""

import json

from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import utils


class CAMPRESET_OT_export(Operator, ExportHelper):
    """Write the preset library to a JSON file"""

    bl_idname = "cam_preset.export"
    bl_label = "Export Presets"

    filename_ext = ".json"

    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context):
        prefs = utils.storage(context)
        return prefs is not None and len(prefs.presets) > 0

    def execute(self, context):
        prefs = utils.storage(context)
        payload = {
            "schema": utils.SCHEMA_VERSION,
            "presets": [utils.preset_to_dict(preset) for preset in prefs.presets],
        }
        try:
            with open(self.filepath, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError as error:
            self.report({'ERROR'}, "Could not write file: {}".format(error))
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            "Exported {} preset(s) to {}".format(len(prefs.presets), self.filepath),
        )
        return {'FINISHED'}


class CAMPRESET_OT_load(Operator, ImportHelper):
    """Append presets from a JSON file to the library"""

    bl_idname = "cam_preset.load"
    bl_label = "Load Presets"

    filename_ext = ".json"

    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context):
        return utils.storage(context) is not None

    def execute(self, context):
        try:
            entries = utils.load_json_file(self.filepath)
        except OSError as error:
            self.report({'ERROR'}, "Could not read file: {}".format(error))
            return {'CANCELLED'}
        except ValueError as error:
            self.report({'ERROR'}, "Invalid JSON: {}".format(error))
            return {'CANCELLED'}

        prefs = utils.storage(context)
        added = utils.append_presets(prefs.presets, entries)
        if added:
            utils.set_active_index(context, len(prefs.presets) - 1)
            utils.tag_redraw()
            self.report({'INFO'}, "Imported {} preset(s)".format(added))
        else:
            self.report({'WARNING'}, "No presets found in the file")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (CAMPRESET_OT_export, CAMPRESET_OT_load)
