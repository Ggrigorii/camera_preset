"""Core camera state capture / restore logic.

Everything that touches ``bpy.types.Object`` or ``bpy.types.Camera`` lives here so
that the operators stay thin and every apply mode (hard set, keyframe, partial,
smooth) shares one implementation.
"""

import json
import os
import time

import bpy
from mathutils import Matrix, Quaternion

from .properties import CHANNEL_KEYS, PRESET_FIELDS

DEFAULTS_FILE = "defaults.json"
SCHEMA_VERSION = 1

VECTOR_FIELDS = {"matrix_basis", "delta_matrix", "controller_matrix"}
BOOL_FIELDS = {"use_dof", "has_focus_object"}
STRING_FIELDS = {
    "name",
    "camera_name",
    "controller_name",
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


# ---------------------------------------------------------------------------
# matrix helpers
# ---------------------------------------------------------------------------

def flat_from_matrix(matrix):
    return [value for row in matrix for value in row]


def matrix_from_flat(values):
    values = tuple(values)
    if len(values) != 16:
        return Matrix.Identity(4)
    return Matrix((
        values[0:4],
        values[4:8],
        values[8:12],
        values[12:16],
    ))


def _delta_matrix(camera):
    mode = camera.rotation_mode
    if mode == 'QUATERNION':
        quat = camera.delta_rotation_quaternion
    elif mode == 'AXIS_ANGLE':
        angle, *axis = camera.delta_rotation_axis_angle
        quat = Quaternion(tuple(axis), angle) if angle else Quaternion()
    else:
        quat = camera.delta_rotation_euler.to_quaternion()
    return Matrix.LocRotScale(camera.delta_location, quat, camera.delta_scale)


def _apply_delta(camera, matrix):
    location, quat, scale = matrix.decompose()
    camera.delta_location = location
    camera.delta_scale = scale
    mode = camera.rotation_mode
    if mode == 'QUATERNION':
        camera.delta_rotation_quaternion = quat
    elif mode == 'AXIS_ANGLE':
        axis = quat.axis
        camera.delta_rotation_axis_angle = (quat.angle, axis[0], axis[1], axis[2])
    else:
        camera.delta_rotation_euler = quat.to_euler(mode)


def rotation_path(camera):
    mode = camera.rotation_mode
    if mode == 'QUATERNION':
        return 'rotation_quaternion'
    if mode == 'AXIS_ANGLE':
        return 'rotation_axis_angle'
    return 'rotation_euler'


# ---------------------------------------------------------------------------
# storage: add-on preferences are shared by every window and every .blend
# ---------------------------------------------------------------------------

def get_prefs(context=None):
    context = context or bpy.context
    preferences = getattr(context, "preferences", None)
    if preferences is None:
        return None
    addon = preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def storage(context=None):
    """Return the preferences object holding the preset library, or None."""
    prefs = get_prefs(context)
    if prefs is None or not hasattr(prefs, "presets"):
        return None
    return prefs


def preset_list(context=None):
    prefs = storage(context)
    return prefs.presets if prefs is not None else None


def active_index(context=None):
    prefs = storage(context)
    return prefs.presets_index if prefs is not None else 0


def set_active_index(context, index):
    prefs = storage(context)
    if prefs is not None:
        prefs.presets_index = index


def clamp_index(context):
    prefs = storage(context)
    if prefs is None:
        return 0
    count = len(prefs.presets)
    if count == 0:
        prefs.presets_index = 0
    elif prefs.presets_index >= count:
        prefs.presets_index = count - 1
    elif prefs.presets_index < 0:
        prefs.presets_index = 0
    return prefs.presets_index


def _pref(name, default):
    prefs = get_prefs()
    if prefs is None:
        return default
    return getattr(prefs, name, default)


def retarget_mode():
    return _pref("retarget_mode", 'SCENE')


def smooth_duration():
    return _pref("smooth_seconds", 0.35)


# ---------------------------------------------------------------------------
# object resolution
# ---------------------------------------------------------------------------

def _usable_camera(name):
    if not name:
        return None
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type == 'CAMERA':
        return obj
    return None


def resolve_camera(scene, preset=None, mode=None):
    """Pick the camera a preset should be applied to."""
    mode = mode or retarget_mode()
    if preset is not None:
        if mode == 'STORED':
            stored = _usable_camera(preset.camera_name)
            if stored is not None:
                return stored
        else:
            active = scene.camera
            if active is not None and active.type == 'CAMERA':
                return active
        stored = _usable_camera(preset.camera_name)
        if stored is not None:
            return stored
    active = scene.camera
    if active is not None and active.type == 'CAMERA':
        return active
    return None


def resolve_controller(scene, preset=None):
    """Object driving the camera through constraints, if any."""
    name = preset.controller_name if preset is not None else ""
    if name:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            return obj
    return getattr(scene, "cam_presets_controller", None)


# ---------------------------------------------------------------------------
# capture / apply
# ---------------------------------------------------------------------------

def capture_state(camera, preset, controller=None):
    """Copy the full camera state (and its rig controller) into a preset."""
    preset.camera_name = camera.name
    preset.rotation_mode = camera.rotation_mode
    preset.matrix_basis = flat_from_matrix(camera.matrix_basis)
    preset.delta_matrix = flat_from_matrix(_delta_matrix(camera))

    if controller is not None:
        preset.controller_name = controller.name
        preset.controller_matrix = flat_from_matrix(controller.matrix_basis)
    else:
        preset.controller_name = ""
        preset.controller_matrix = (1.0, 0.0, 0.0, 0.0,
                                    0.0, 1.0, 0.0, 0.0,
                                    0.0, 0.0, 1.0, 0.0,
                                    0.0, 0.0, 0.0, 1.0)

    data = camera.data
    preset.camera_type = data.type
    preset.lens = data.lens
    preset.sensor_width = data.sensor_width
    preset.sensor_height = data.sensor_height
    preset.sensor_fit = data.sensor_fit
    preset.shift_x = data.shift_x
    preset.shift_y = data.shift_y
    preset.clip_start = data.clip_start
    preset.clip_end = data.clip_end
    preset.ortho_scale = data.ortho_scale
    preset.panorama_type = getattr(data, "panorama_type", "") or ""

    dof = data.dof
    preset.use_dof = dof.use_dof
    preset.focus_distance = dof.focus_distance
    preset.aperture_fstop = dof.aperture_fstop
    preset.has_focus_object = dof.focus_object is not None
    preset.focus_object_name = dof.focus_object.name if dof.focus_object else ""


def has_animation(obj):
    animation = obj.animation_data
    if animation is None:
        return False
    return animation.action is not None or len(animation.drivers) > 0


def describe_risks(camera, controller=None):
    """Warnings about state that overrides plain property values."""
    risks = []
    if controller is None:
        if len(camera.constraints) > 0:
            risks.append(
                "Camera has constraints; pick a Controller object or its transform "
                "will be overridden"
            )
        if has_animation(camera):
            risks.append(
                "Camera has animation or drivers; values may be overridden on frame change"
            )
    elif has_animation(controller):
        risks.append(
            "Controller has animation or drivers; values may be overridden on frame change"
        )
    return risks


def apply_state(camera, preset, channels='ALL', keyframe=False, frame=None,
                controller=None):
    """Apply a preset. Returns ``(touched, warnings)``.

    ``touched`` is a list of ``(owner, data_path)`` pairs used for keyframing.
    When a controller is given, the transform goes to the controller and the
    camera keeps its constraint driven orientation.
    """
    channels = channels if channels in CHANNEL_KEYS else 'ALL'
    warnings = []
    touched = []

    if channels in {'ALL', 'TRANSFORM'}:
        if controller is not None:
            controller.matrix_basis = matrix_from_flat(preset.controller_matrix)
            touched.append((controller, "location"))
            touched.append((controller, "scale"))
            touched.append((controller, rotation_path(controller)))
        else:
            camera.rotation_mode = preset.rotation_mode or 'XYZ'
            camera.matrix_basis = matrix_from_flat(preset.matrix_basis)
            _apply_delta(camera, matrix_from_flat(preset.delta_matrix))
            touched.append((camera, "location"))
            touched.append((camera, "scale"))
            touched.append((camera, rotation_path(camera)))

    data = camera.data

    if channels in {'ALL', 'OPTICS'}:
        if data.type != preset.camera_type:
            data.type = preset.camera_type
        data.lens = max(1e-3, preset.lens)
        data.sensor_width = max(1e-3, preset.sensor_width)
        data.sensor_height = max(1e-3, preset.sensor_height)
        data.sensor_fit = preset.sensor_fit or 'AUTO'
        data.shift_x = preset.shift_x
        data.shift_y = preset.shift_y
        data.clip_start = max(1e-6, preset.clip_start)
        data.clip_end = max(data.clip_start + 1e-3, preset.clip_end)
        data.ortho_scale = max(1e-6, preset.ortho_scale)
        if preset.panorama_type:
            try:
                data.panorama_type = preset.panorama_type
            except (TypeError, ValueError):
                warnings.append(
                    "Panorama type '{}' is not supported by this Blender version".format(
                        preset.panorama_type
                    )
                )
        for path in (
            "lens",
            "sensor_width",
            "sensor_height",
            "shift_x",
            "shift_y",
            "clip_start",
            "clip_end",
            "ortho_scale",
        ):
            touched.append((data, path))

    if channels in {'ALL', 'DOF'}:
        dof = data.dof
        dof.use_dof = preset.use_dof
        dof.focus_distance = max(0.0, preset.focus_distance)
        dof.aperture_fstop = max(0.0, preset.aperture_fstop)

        focus_object = None
        if preset.has_focus_object and preset.focus_object_name:
            focus_object = bpy.data.objects.get(preset.focus_object_name)
            if focus_object is None:
                # The library is global: a preset may come from another .blend
                # file where this object exists. Keep whatever the camera uses
                # now instead of silently destroying a working setup.
                if dof.focus_object is not None:
                    focus_object = dof.focus_object
                    warnings.append(
                        "Focus object '{}' is not in this file; kept '{}'".format(
                            preset.focus_object_name, focus_object.name
                        )
                    )
                else:
                    warnings.append(
                        "Focus object '{}' is not in this file; focus distance is used".format(
                            preset.focus_object_name
                        )
                    )
        dof.focus_object = focus_object
        touched.append((data, "dof.use_dof"))
        touched.append((data, "dof.focus_distance"))
        touched.append((data, "dof.aperture_fstop"))

    if keyframe:
        if frame is None:
            frame = bpy.context.scene.frame_current
        for owner, path in touched:
            try:
                owner.keyframe_insert(data_path=path, frame=frame)
            except (RuntimeError, TypeError, KeyError):
                continue

    return touched, warnings


# ---------------------------------------------------------------------------
# redraw helpers
# ---------------------------------------------------------------------------

def tag_redraw():
    """Ask every window to redraw so other windows show the new preset list."""
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            try:
                area.tag_redraw()
            except (ReferenceError, RuntimeError):
                continue


# ---------------------------------------------------------------------------
# smooth transform transition (transform only, by design)
# ---------------------------------------------------------------------------

_smooth_state = None


def is_smoothing():
    return _smooth_state is not None


def stop_smooth():
    global _smooth_state
    _smooth_state = None


def _smooth_target(camera, preset, controller):
    if controller is not None:
        return controller, matrix_from_flat(preset.controller_matrix)
    camera.rotation_mode = preset.rotation_mode or 'XYZ'
    return camera, matrix_from_flat(preset.matrix_basis)


def start_smooth(camera, preset, controller=None):
    """Animate the transform towards the preset using a timer."""
    global _smooth_state

    stop_smooth()
    target_object, target_matrix = _smooth_target(camera, preset, controller)
    if controller is None:
        _apply_delta(camera, matrix_from_flat(preset.delta_matrix))

    target_location, target_quat, target_scale = target_matrix.decompose()
    start_location, start_quat, start_scale = target_object.matrix_basis.decompose()

    _smooth_state = {
        "object": target_object,
        "started": time.perf_counter(),
        "duration": max(0.05, float(smooth_duration())),
        "location": (start_location.copy(), target_location.copy()),
        "rotation": (start_quat.copy(), target_quat.copy()),
        "scale": (start_scale.copy(), target_scale.copy()),
    }

    if not bpy.app.timers.is_registered(_smooth_tick):
        bpy.app.timers.register(_smooth_tick, first_interval=0.0, persistent=False)


def _smooth_tick():
    global _smooth_state

    state = _smooth_state
    if state is None:
        return None

    target = state["object"]
    if target is None or target.name not in bpy.data.objects:
        stop_smooth()
        return None

    elapsed = time.perf_counter() - state["started"]
    progress = min(1.0, elapsed / state["duration"])
    eased = progress * progress * (3.0 - 2.0 * progress)  # smoothstep

    try:
        location = state["location"][0].lerp(state["location"][1], eased)
        rotation = state["rotation"][0].slerp(state["rotation"][1], eased)
        scale = state["scale"][0].lerp(state["scale"][1], eased)
        target.matrix_basis = Matrix.LocRotScale(location, rotation, scale)
    except (ReferenceError, RuntimeError, ValueError):
        stop_smooth()
        return None

    view_layer = getattr(bpy.context, "view_layer", None)
    if view_layer is not None:
        view_layer.update()
    tag_redraw()

    if progress >= 1.0:
        stop_smooth()
        return None
    return 1.0 / 60.0


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------

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


def load_json_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    entries = payload.get("presets") if isinstance(payload, dict) else payload
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(
        entries, list
    ) else []


def append_presets(presets, entries):
    added = 0
    for entry in entries:
        preset = presets.add()
        dict_to_preset(preset, entry)
        preset.name = unique_name(presets, preset.name or "Preset", exclude=preset)
        added += 1
    return added


# ---------------------------------------------------------------------------
# defaults, migration
# ---------------------------------------------------------------------------

def _defaults_entries():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULTS_FILE)
    if not os.path.exists(path):
        return []
    try:
        return load_json_file(path)
    except (OSError, ValueError):
        return []


def seed_defaults(prefs):
    entries = _defaults_entries()
    if not entries:
        return 0
    return append_presets(prefs.presets, entries)


def migrate_legacy(prefs):
    """Copy presets stored on Scene by version 1.1 into the global library."""
    moved = 0
    for scene in bpy.data.scenes:
        if not hasattr(scene, "cam_presets"):
            continue
        for legacy in scene.cam_presets:
            preset = prefs.presets.add()
            preset.name = legacy.name
            for field in PRESET_FIELDS:
                value = getattr(legacy, field, None)
                if value is None:
                    continue
                if hasattr(value, "__len__") and not isinstance(value, str):
                    setattr(preset, field, tuple(value))
                else:
                    setattr(preset, field, value)
            preset.name = unique_name(prefs.presets, preset.name, exclude=preset)
            moved += 1
    return moved


def bootstrap(context=None):
    """Seed the global library on first run and migrate legacy scene presets.

    Safe to call from ``register()``: while Blender enables the add-on the
    ``bpy.data`` access is restricted, so the work is retried later on the first
    panel draw or operator call.
    """
    global _bootstrap_done
    if _bootstrap_done:
        return
    prefs = storage(context)
    if prefs is None:
        return
    try:
        _run_bootstrap(prefs)
    except (AttributeError, RuntimeError, ReferenceError):
        return
    _bootstrap_done = True
    try:
        tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


_bootstrap_done = False


def reset_bootstrap():
    global _bootstrap_done
    _bootstrap_done = False


def _run_bootstrap(prefs):
    if len(prefs.presets) > 0:
        prefs.seeded = True
        return
    if migrate_legacy(prefs) > 0:
        prefs.seeded = True
        return
    if not prefs.seeded:
        seed_defaults(prefs)
        prefs.seeded = True


# ---------------------------------------------------------------------------
# preset helpers
# ---------------------------------------------------------------------------

def copy_preset(source, target, include_name=True):
    for field in PRESET_FIELDS:
        if field == "name" and not include_name:
            continue
        value = getattr(source, field)
        if hasattr(value, "__len__") and not isinstance(value, str):
            setattr(target, field, tuple(value))
        else:
            setattr(target, field, value)


def unique_name(collection, base, exclude=None):
    base = base or "Preset"
    excluded = exclude.as_pointer() if exclude is not None else None
    names = {
        item.name
        for item in collection
        if excluded is None or item.as_pointer() != excluded
    }
    if base not in names:
        return base
    index = 1
    while "{}.{:03d}".format(base, index) in names:
        index += 1
    return "{}.{:03d}".format(base, index)


def reorder_presets(presets, from_index, to_index):
    """Move a preset inside the collection. Returns the new index."""
    count = len(presets)
    if count < 2:
        return from_index
    from_index = max(0, min(count - 1, from_index))
    to_index = max(0, min(count - 1, to_index))
    if from_index == to_index:
        return from_index

    move = getattr(presets, "move", None)
    if move is not None:
        try:
            move(from_index, to_index)
            return to_index
        except (AttributeError, RuntimeError, TypeError):
            pass

    order = []
    for preset in presets:
        order.append({field: getattr(preset, field) for field in PRESET_FIELDS})
    item = order.pop(from_index)
    order.insert(to_index, item)
    for index in range(len(presets) - 1, -1, -1):
        presets.remove(index)
    for values in order:
        preset = presets.add()
        for field, value in values.items():
            if hasattr(value, "__len__") and not isinstance(value, str):
                setattr(preset, field, tuple(value))
            else:
                setattr(preset, field, value)
    return to_index
