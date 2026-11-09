"""Camera Preset Manager - quick camera state presets for Blender.

Extension metadata lives in ``blender_manifest.toml``, as required by the
Blender 4.2+ extension format; no legacy add-on metadata dictionary is defined.
"""

import bpy

from . import (  # noqa: F401  (imported for side-effect free registration)
    json_io,
    keymaps,
    operators,
    panels,
    pie,
    preferences,
    properties,
    ui_list,
    utils,
)

CLASSES = (
    *properties.classes,
    *ui_list.classes,
    *pie.classes,
    *operators.classes,
    *json_io.classes,
    *preferences.classes,
    *panels.classes,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    properties.register_scene_properties()
    keymaps.register()


def unregister():
    keymaps.unregister()
    utils.stop_smooth()
    properties.unregister_scene_properties()
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            # Re-registration during extension reload; nothing to undo.
            continue
