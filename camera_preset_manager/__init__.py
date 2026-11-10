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

__version__ = "1.2.1"

CLASSES = (
    *properties.classes,
    *ui_list.classes,
    *pie.classes,
    *operators.classes,
    *json_io.classes,
    *preferences.classes,
    *panels.classes,
)

_bootstrap_attempts = 0
_MAX_BOOTSTRAP_ATTEMPTS = 20


def _bootstrap_timer():
    """Retry the library bootstrap until bpy.data is safe to touch."""
    global _bootstrap_attempts

    function = getattr(utils, "bootstrap", None)
    if function is None:
        print(
            "[Camera Preset Manager] incomplete installation: utils.bootstrap is "
            "missing. Reinstall the extension from the .zip package."
        )
        return None

    try:
        function()
    except Exception as error:  # noqa: BLE001 - never break the UI loop
        print("[Camera Preset Manager] bootstrap failed:", error)
        return None

    if getattr(utils, "_bootstrap_done", False):
        return None

    _bootstrap_attempts += 1
    if _bootstrap_attempts >= _MAX_BOOTSTRAP_ATTEMPTS:
        print("[Camera Preset Manager] bootstrap did not finish; presets are empty")
        return None
    return 1.0


def register():
    global _bootstrap_attempts

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    properties.register_scene_properties()

    # Hotkeys are registered before anything else can fail: a broken library
    # must never take the keymap down with it.
    keymaps.register()

    _bootstrap_attempts = 0
    bootstrap = getattr(utils, "bootstrap", None)
    if bootstrap is None:
        print(
            "[Camera Preset Manager] incomplete installation: utils.bootstrap is "
            "missing. Reinstall the extension from the .zip package."
        )
        return
    try:
        bootstrap()
    except Exception as error:  # noqa: BLE001 - registration must stay alive
        print("[Camera Preset Manager] bootstrap deferred:", error)

    if not getattr(utils, "_bootstrap_done", False):
        if not bpy.app.timers.is_registered(_bootstrap_timer):
            bpy.app.timers.register(_bootstrap_timer, first_interval=1.0)


def unregister():
    if bpy.app.timers.is_registered(_bootstrap_timer):
        bpy.app.timers.unregister(_bootstrap_timer)

    keymaps.unregister()
    utils.stop_smooth()
    utils.reset_bootstrap()
    properties.unregister_scene_properties()
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            # Re-registration during extension reload; nothing to undo.
            continue
