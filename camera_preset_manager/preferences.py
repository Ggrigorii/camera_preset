"""Add-on preferences: also the global preset library storage."""

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
)
from bpy.types import AddonPreferences

from . import keymaps
from .properties import CAMPRESET_PG_preset


def _update_keymaps(self, context):
    keymaps.refresh(self.register_keymaps)


class CAMPRESET_AP_preferences(AddonPreferences):
    bl_idname = __package__

    # --- global preset library, shared by every window and every .blend file ---
    presets: CollectionProperty(type=CAMPRESET_PG_preset)
    presets_index: IntProperty(name="Active Preset", default=0, min=0)
    seeded: BoolProperty(
        name="Defaults Seeded",
        default=False,
        description="Internal flag: factory presets were already loaded",
    )

    register_keymaps: BoolProperty(
        name="Register Hotkeys",
        default=True,
        description="Register the default hotkeys; disable if they clash with your setup",
        update=_update_keymaps,
    )
    retarget_mode: EnumProperty(
        name="Apply To",
        items=[
            ('SCENE', "Active Scene Camera", "Apply presets to the active scene camera"),
            ('STORED', "Camera From Preset", "Apply presets to the camera they were saved from"),
        ],
        default='SCENE',
    )
    smooth_seconds: FloatProperty(
        name="Transition Duration (s)",
        description="Duration of the smooth camera transition in seconds",
        default=0.35,
        min=0.05,
        max=5.0,
    )

    def draw(self, context):
        layout = self.layout

        column = layout.column(align=True)
        column.label(text="Preset library: {} preset(s)".format(len(self.presets)))
        column.label(
            text="Stored in the add-on preferences: shared by all windows and files.",
            icon='INFO',
        )

        column = layout.column(align=True)
        column.prop(self, "register_keymaps")
        if self.register_keymaps:
            box = column.box()
            for binding in keymaps.active_bindings():
                box.label(text=binding)

        layout.prop(self, "retarget_mode")
        layout.prop(self, "smooth_seconds")

        if keymaps.conflicts:
            box = layout.box()
            box.label(text="Hotkey conflicts detected:", icon='ERROR')
            for message in keymaps.conflicts:
                box.label(text=message)


classes = (CAMPRESET_AP_preferences,)
