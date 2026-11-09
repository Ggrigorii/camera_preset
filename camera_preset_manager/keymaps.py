"""Addon keymap registration and conflict detection."""

import bpy

from . import utils

addon_keymaps = []
conflicts = []

# (label, operator idname, event type, modifiers)
DEFAULT_BINDINGS = (
    ("Pie Menu", "wm.call_menu_pie", 'C', {'ctrl': True, 'alt': True}),
    ("Save New Preset", "cam_preset.save", 'S', {'ctrl': True, 'alt': True}),
)

KEYMAP_NAME = "3D View"
SPACE_TYPE = 'VIEW_3D'


def _combo(event_type, modifiers):
    parts = []
    if modifiers.get("ctrl"):
        parts.append("Ctrl")
    if modifiers.get("alt"):
        parts.append("Alt")
    if modifiers.get("shift"):
        parts.append("Shift")
    parts.append(event_type)
    return "+".join(parts)


def find_conflicts():
    """Return human readable conflict descriptions for the default bindings."""
    found = []
    window_manager = bpy.context.window_manager
    if window_manager is None:
        return found

    for config_name in ("user", "default"):
        keyconfig = getattr(window_manager.keyconfigs, config_name, None)
        if keyconfig is None:
            continue
        for keymap in keyconfig.keymaps:
            if keymap.name != KEYMAP_NAME:
                continue
            for item in keymap.keymap_items:
                for _, _, event_type, modifiers in DEFAULT_BINDINGS:
                    if (
                        item.type == event_type
                        and item.ctrl == modifiers.get("ctrl", False)
                        and item.alt == modifiers.get("alt", False)
                        and item.shift == modifiers.get("shift", False)
                    ):
                        found.append(
                            "{} is already used by '{}' in the {} keyconfig".format(
                                _combo(event_type, modifiers), item.idname, config_name
                            )
                        )
    return found


def register(enabled=None):
    global conflicts

    unregister()

    if enabled is None:
        prefs = utils.get_prefs()
        enabled = True if prefs is None else getattr(prefs, "register_keymaps", True)
    if not enabled:
        conflicts = []
        return []

    window_manager = bpy.context.window_manager
    if window_manager is None:
        return []
    keyconfig = window_manager.keyconfigs.addon
    if keyconfig is None:
        return []

    keymap = keyconfig.keymaps.new(name=KEYMAP_NAME, space_type=SPACE_TYPE)

    operation = keymap.keymap_items.new(
        "wm.call_menu_pie", 'C', 'PRESS', ctrl=True, alt=True
    )
    operation.properties.name = "CAMPRESET_MT_pie"
    addon_keymaps.append((keymap, operation))

    operation = keymap.keymap_items.new(
        "cam_preset.save", 'S', 'PRESS', ctrl=True, alt=True
    )
    addon_keymaps.append((keymap, operation))

    conflicts = find_conflicts()
    for message in conflicts:
        print("[Camera Preset Manager] " + message)
    return conflicts


def refresh(enabled=None):
    return register(enabled)


def unregister():
    global conflicts

    window_manager = bpy.context.window_manager
    if window_manager is not None:
        for keymap, item in list(addon_keymaps):
            try:
                keymap.keymap_items.remove(item)
            except (RuntimeError, ReferenceError):
                continue
    addon_keymaps.clear()
    conflicts = []


def active_bindings():
    return ["{} — {}".format(label, _combo(event_type, modifiers))
            for label, _, event_type, modifiers in DEFAULT_BINDINGS]
