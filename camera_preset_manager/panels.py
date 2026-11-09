"""Sidebar panel for Camera Preset Manager."""

from bpy.types import Panel


class CAMPRESET_PT_panel(Panel):
    bl_idname = "CAMPRESET_PT_panel"
    bl_label = "Camera Presets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera Presets"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        presets = scene.cam_presets
        camera = scene.camera

        box = layout.box()
        column = box.column(align=True)
        if camera is None:
            column.label(text="No active scene camera", icon='ERROR')
        else:
            column.label(text="Target: {}".format(camera.name), icon='CAMERA_DATA')

        row = layout.row(align=True)
        row.operator("cam_preset.save", text="Save New", icon='ADD')
        row.operator("cam_preset.update", text="Update", icon='FILE_REFRESH')
        row = layout.row()
        operation = row.operator(
            "wm.call_menu_pie", text="Pie Menu", icon='COLLAPSEMENU'
        )
        operation.name = "CAMPRESET_MT_pie"

        layout.template_list(
            "CAMPRESET_UL_list",
            "",
            scene,
            "cam_presets",
            scene,
            "cam_presets_index",
            rows=6,
        )

        if presets:
            row = layout.row(align=True)
            row.operator("cam_preset.apply", text="Apply", icon='PLAY')
            row.operator("cam_preset.duplicate", text="", icon='DUPLICATE')
            operation = row.operator("cam_preset.move", text="", icon='TRIA_UP')
            operation.direction = 'UP'
            operation = row.operator("cam_preset.move", text="", icon='TRIA_DOWN')
            operation.direction = 'DOWN'
            row.operator("cam_preset.delete", text="", icon='X')

            column = layout.column(align=True)
            column.prop(scene, "cam_presets_channels", text="")
            row = column.row(align=True)
            row.prop(scene, "cam_presets_keyframe", text="Keyframe", toggle=True)
            row.prop(scene, "cam_presets_smooth", text="Smooth", toggle=True)

            index = min(scene.cam_presets_index, len(presets) - 1)
            preset = presets[index]
            box = layout.box()
            column = box.column(align=True)
            if preset.camera_name:
                column.label(text="From: {}".format(preset.camera_name))
            if preset.camera_type == 'PERSP':
                column.label(text="Lens: {:.1f} mm".format(preset.lens))
            elif preset.camera_type == 'ORTHO':
                column.label(text="Ortho Scale: {:.3f}".format(preset.ortho_scale))
            else:
                column.label(text="Panoramic")
            if preset.use_dof:
                column.label(
                    text="DOF: f/{:.1f}".format(preset.aperture_fstop)
                )

            row = layout.row()
            row.operator(
                "cam_preset.reset_scene", text="Remove All Presets", icon='TRASH'
            )
        else:
            column = layout.column(align=True)
            column.label(text="No presets yet.", icon='INFO')
            column.label(text="Set up your camera and press Save New.")

        row = layout.row(align=True)
        row.operator("cam_preset.export", text="Export", icon='EXPORT')
        row.operator("cam_preset.load", text="Load", icon='IMPORT')

        layout.label(text="Pie: Ctrl+Alt+C    Save: Ctrl+Alt+S", icon='INFO')


classes = (CAMPRESET_PT_panel,)
