"""Operators for saving, applying and managing camera presets."""

from bpy.props import EnumProperty, IntProperty
from bpy.types import Operator

from . import utils


def _ensure_bootstrap(context):
    """Seed the library if registration could not do it yet.

    Tolerates an out-of-date ``utils`` module left by a partial reinstall, so a
    stale file cannot raise AttributeError on every click.
    """
    function = getattr(utils, "bootstrap", None)
    if function is not None:
        function(context)


def _presets(context):
    _ensure_bootstrap(context)
    return utils.preset_list(context)


def _active_preset(context):
    presets = utils.preset_list(context)
    if not presets:
        return None
    index = utils.active_index(context)
    if index < 0 or index >= len(presets):
        index = utils.clamp_index(context)
    return presets[index]


def _scene(context):
    return getattr(context, "scene", None)


def _scene_poll(context):
    return _scene(context) is not None


def _storage_poll(context):
    return _scene_poll(context) and utils.storage(context) is not None


def _warn(operator, messages):
    if messages:
        operator.report({'WARNING'}, "; ".join(messages))


def _controller(context):
    scene = _scene(context)
    return getattr(scene, "cam_presets_controller", None)


class CAMPRESET_OT_save(Operator):
    """Save the current camera state as a new preset"""

    bl_idname = "cam_preset.save"
    bl_label = "Save New Preset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _storage_poll(context)

    def execute(self, context):
        scene = context.scene
        presets = _presets(context)
        if presets is None:
            self.report({'ERROR'}, "Preset library is unavailable")
            return {'CANCELLED'}

        camera = scene.camera
        if camera is None or camera.type != 'CAMERA':
            self.report({'WARNING'}, "No active scene camera")
            return {'CANCELLED'}

        utils.stop_smooth()
        base = "Preset {}".format(len(presets) + 1)
        preset = presets.add()
        preset.name = utils.unique_name(presets, base, exclude=preset)
        utils.capture_state(camera, preset, controller=_controller(context))
        utils.set_active_index(context, len(presets) - 1)
        utils.tag_redraw()
        self.report({'INFO'}, "Saved preset '{}'".format(preset.name))
        return {'FINISHED'}


class CAMPRESET_OT_update(Operator):
    """Overwrite the active preset with the current camera state"""

    bl_idname = "cam_preset.update"
    bl_label = "Update Active Preset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not _storage_poll(context):
            return False
        presets = utils.preset_list(context)
        return bool(presets) and context.scene.camera is not None

    def execute(self, context):
        scene = context.scene
        preset = _active_preset(context)
        if preset is None:
            self.report({'WARNING'}, "No active preset")
            return {'CANCELLED'}

        camera = scene.camera
        if camera is None or camera.type != 'CAMERA':
            self.report({'WARNING'}, "No active scene camera")
            return {'CANCELLED'}

        utils.stop_smooth()
        utils.capture_state(camera, preset, controller=_controller(context))
        utils.tag_redraw()
        self.report({'INFO'}, "Updated preset '{}'".format(preset.name))
        return {'FINISHED'}


class CAMPRESET_OT_apply(Operator):
    """Apply a stored camera preset"""

    bl_idname = "cam_preset.apply"
    bl_label = "Apply Preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset_index: IntProperty(
        name="Preset Index",
        default=-1,
        min=-1,
        description="Preset to apply; -1 uses the active list item",
    )

    @classmethod
    def poll(cls, context):
        return _storage_poll(context)

    def execute(self, context):
        scene = context.scene
        presets = _presets(context)
        if not presets:
            self.report({'WARNING'}, "No camera presets to apply")
            return {'CANCELLED'}

        if self.preset_index >= 0:
            index = self.preset_index
            if index >= len(presets):
                self.report(
                    {'WARNING'},
                    "Preset index {} is out of range ({} presets)".format(
                        index, len(presets)
                    ),
                )
                return {'CANCELLED'}
        else:
            index = utils.active_index(context)
            if index < 0 or index >= len(presets):
                self.report({'WARNING'}, "No active preset selected")
                return {'CANCELLED'}

        preset = presets[index]
        camera = utils.resolve_camera(scene, preset)
        if camera is None:
            self.report({'WARNING'}, "No camera available to apply the preset to")
            return {'CANCELLED'}

        controller = utils.resolve_controller(scene, preset)
        channels = scene.cam_presets_channels
        keyframe = scene.cam_presets_keyframe
        smooth = scene.cam_presets_smooth
        warnings = utils.describe_risks(camera, controller)

        if keyframe:
            utils.stop_smooth()
            _, apply_warnings = utils.apply_state(
                camera, preset, channels=channels, keyframe=True, controller=controller
            )
            warnings.extend(apply_warnings)
        elif smooth and channels in {'ALL', 'TRANSFORM'} and not utils.has_animation(
            controller if controller is not None else camera
        ):
            if channels == 'ALL':
                _, optics_warnings = utils.apply_state(camera, preset, channels='OPTICS')
                _, dof_warnings = utils.apply_state(camera, preset, channels='DOF')
                warnings.extend(optics_warnings)
                warnings.extend(dof_warnings)
            utils.start_smooth(camera, preset, controller=controller)
        else:
            utils.stop_smooth()
            _, apply_warnings = utils.apply_state(
                camera, preset, channels=channels, controller=controller
            )
            warnings.extend(apply_warnings)

        utils.set_active_index(context, index)
        utils.tag_redraw()
        _warn(self, warnings)
        return {'FINISHED'}


class CAMPRESET_OT_delete(Operator):
    """Delete the active preset"""

    bl_idname = "cam_preset.delete"
    bl_label = "Delete Preset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not _storage_poll(context):
            return False
        return len(utils.preset_list(context)) > 0

    def execute(self, context):
        presets = _presets(context)
        index = utils.active_index(context)
        if index < 0 or index >= len(presets):
            self.report({'WARNING'}, "No active preset")
            return {'CANCELLED'}

        utils.stop_smooth()
        name = presets[index].name
        presets.remove(index)
        utils.clamp_index(context)
        utils.tag_redraw()
        self.report({'INFO'}, "Deleted preset '{}'".format(name))
        return {'FINISHED'}


class CAMPRESET_OT_duplicate(Operator):
    """Duplicate the active preset"""

    bl_idname = "cam_preset.duplicate"
    bl_label = "Duplicate Preset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not _storage_poll(context):
            return False
        return len(utils.preset_list(context)) > 0

    def execute(self, context):
        presets = _presets(context)
        source = _active_preset(context)
        if source is None:
            self.report({'WARNING'}, "No active preset")
            return {'CANCELLED'}

        target = presets.add()
        utils.copy_preset(source, target, include_name=False)
        target.name = utils.unique_name(presets, source.name, exclude=target)
        utils.set_active_index(context, len(presets) - 1)
        utils.tag_redraw()
        return {'FINISHED'}


class CAMPRESET_OT_move(Operator):
    """Move the active preset up or down in the list"""

    bl_idname = "cam_preset.move"
    bl_label = "Move Preset"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(
        name="Direction",
        items=[
            ('UP', "Up", "Move the preset up"),
            ('DOWN', "Down", "Move the preset down"),
        ],
        default='UP',
    )

    @classmethod
    def poll(cls, context):
        if not _storage_poll(context):
            return False
        return len(utils.preset_list(context)) > 1

    def execute(self, context):
        presets = _presets(context)
        index = utils.active_index(context)
        target = index - 1 if self.direction == 'UP' else index + 1
        new_index = utils.reorder_presets(presets, index, target)
        utils.set_active_index(context, new_index)
        utils.tag_redraw()
        return {'FINISHED'}


class CAMPRESET_OT_reset_scene(Operator):
    """Remove every preset from the library"""

    bl_idname = "cam_preset.reset_scene"
    bl_label = "Remove All Presets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not _storage_poll(context):
            return False
        return len(utils.preset_list(context)) > 0

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        presets = _presets(context)
        for index in range(len(presets) - 1, -1, -1):
            presets.remove(index)
        utils.set_active_index(context, 0)
        utils.tag_redraw()
        return {'FINISHED'}


class CAMPRESET_OT_restore_defaults(Operator):
    """Restore the factory preset library"""

    bl_idname = "cam_preset.restore_defaults"
    bl_label = "Restore Default Presets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _storage_poll(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        prefs = utils.storage(context)
        if prefs is None:
            return {'CANCELLED'}
        added = utils.seed_defaults(prefs)
        prefs.seeded = True
        if added:
            utils.set_active_index(context, len(prefs.presets) - 1)
        utils.tag_redraw()
        self.report({'INFO'}, "Added {} default preset(s)".format(added))
        return {'FINISHED'}


classes = (
    CAMPRESET_OT_save,
    CAMPRESET_OT_update,
    CAMPRESET_OT_apply,
    CAMPRESET_OT_delete,
    CAMPRESET_OT_duplicate,
    CAMPRESET_OT_move,
    CAMPRESET_OT_reset_scene,
    CAMPRESET_OT_restore_defaults,
)
