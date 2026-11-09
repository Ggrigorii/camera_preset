"""Pie menu with the live preset list."""

from bpy.types import Menu

from . import utils

MAX_SLOTS = 8


class CAMPRESET_MT_pie(Menu):
    bl_idname = "CAMPRESET_MT_pie"
    bl_label = "Camera Presets"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        prefs = utils.storage(context)
        if prefs is None:
            pie.label(text="Enable the add-on first", icon='ERROR')
            return

        presets = prefs.presets
        count = len(presets)
        active_index = prefs.presets_index

        slots = []
        if count == 0:
            slots.append(("defaults", None, "Add Default Presets"))
        else:
            visible = min(count, MAX_SLOTS)
            for index in range(visible):
                slots.append(("apply", index, presets[index].name))
            if count > MAX_SLOTS:
                slots[-1] = ("more", None, "All Presets ({})".format(count))

        if count < MAX_SLOTS:
            slots.append(("save", None, "Save New Preset"))
        if count < MAX_SLOTS - 1:
            slots.append(("update", None, "Update Current"))

        while len(slots) < MAX_SLOTS:
            slots.append(("separator", None, ""))

        for kind, index, text in slots:
            if kind == "apply":
                icon = 'LAYER_ACTIVE' if index == active_index else 'BLANK1'
                operation = pie.operator("cam_preset.apply", text=text, icon=icon)
                operation.preset_index = index
            elif kind == "save":
                pie.operator("cam_preset.save", text=text, icon='ADD')
            elif kind == "update":
                pie.operator("cam_preset.update", text=text, icon='FILE_REFRESH')
            elif kind == "defaults":
                pie.operator("cam_preset.restore_defaults", text=text, icon='FILE_NEW')
            elif kind == "more":
                pie.menu("CAMPRESET_MT_list", text=text, icon='COLLAPSEMENU')
            else:
                pie.separator()


class CAMPRESET_MT_list(Menu):
    """Flat list of every preset, used for large collections."""

    bl_idname = "CAMPRESET_MT_list"
    bl_label = "Camera Presets"

    def draw(self, context):
        layout = self.layout
        prefs = utils.storage(context)
        if prefs is None:
            layout.label(text="Enable the add-on first", icon='ERROR')
            return

        presets = prefs.presets
        active_index = prefs.presets_index

        if not presets:
            layout.label(text="No presets yet", icon='INFO')
        else:
            for index, preset in enumerate(presets):
                icon = 'LAYER_ACTIVE' if index == active_index else 'BLANK1'
                operation = layout.operator(
                    "cam_preset.apply", text=preset.name, icon=icon
                )
                operation.preset_index = index

        layout.separator()
        layout.operator("cam_preset.save", text="Save New Preset", icon='ADD')
        layout.operator("cam_preset.update", text="Update Current", icon='FILE_REFRESH')


classes = (CAMPRESET_MT_pie, CAMPRESET_MT_list)
