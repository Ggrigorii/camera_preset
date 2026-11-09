"""Core camera state capture / restore logic.

Everything that touches ``bpy.types.Object`` or ``bpy.types.Camera`` lives here so
that the operators stay thin and every apply mode (hard set, keyframe, partial,
smooth) shares one implementation.
"""

import time

import bpy
from mathutils import Matrix, Quaternion

from .properties import CHANNEL_KEYS, PRESET_FIELDS

_ROTATION_PREFIX = 'rotation_'


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
# preferences / camera resolution
# ---------------------------------------------------------------------------

def get_prefs(context=None):
    context = context or bpy.context
    preferences = getattr(context, "preferences", None)
    if preferences is None:
        return None
    addon = preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def _pref(name, default):
    prefs = get_prefs()
    if prefs is None:
        return default
    return getattr(prefs, name, default)


def retarget_mode():
    return _pref("retarget_mode", 'SCENE')


def smooth_duration():
    return _pref("smooth_seconds", 0.35)


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
        # Fallbacks keep the operation useful instead of silently doing nothing.
        stored = _usable_camera(preset.camera_name)
        if stored is not None:
            return stored
    active = scene.camera
    if active is not None and active.type == 'CAMERA':
        return active
    return None


# ---------------------------------------------------------------------------
# capture / apply
# ---------------------------------------------------------------------------

def capture_state(camera, preset):
    """Copy the full camera state into a preset property group."""
    preset.camera_name = camera.name
    preset.rotation_mode = camera.rotation_mode
    preset.matrix_basis = flat_from_matrix(camera.matrix_basis)
    preset.delta_matrix = flat_from_matrix(_delta_matrix(camera))

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
    preset.focus_object_name = dof.focus_object.name if dof.focus_object else ""


def has_animation(camera):
    animation = camera.animation_data
    if animation is None:
        return False
    return animation.action is not None or len(animation.drivers) > 0


def describe_risks(camera):
    """Human readable warnings about state that overrides plain property values."""
    risks = []
    if has_animation(camera):
        risks.append(
            "Camera has animation or drivers; values may be overridden on frame change"
        )
    if len(camera.constraints) > 0:
        risks.append("Camera has constraints that may override its transform")
    return risks


def apply_state(camera, preset, channels='ALL', keyframe=False, frame=None):
    """Apply a preset to a camera. Returns ``(touched, warnings)``.

    ``touched`` is a list of ``(owner, data_path)`` pairs used for keyframing.
    """
    channels = channels if channels in CHANNEL_KEYS else 'ALL'
    warnings = []
    touched = []

    if channels in {'ALL', 'TRANSFORM'}:
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
        if preset.focus_object_name:
            focus_object = bpy.data.objects.get(preset.focus_object_name)
            if focus_object is None:
                warnings.append(
                    "Focus object '{}' was not found; focus distance is used instead".format(
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
# smooth transform transition (transform only, by design)
# ---------------------------------------------------------------------------

_smooth_state = None


def is_smoothing():
    return _smooth_state is not None


def stop_smooth():
    global _smooth_state
    _smooth_state = None


def start_smooth(camera, preset):
    """Animate the camera transform towards the preset using a timer."""
    global _smooth_state

    stop_smooth()
    camera.rotation_mode = preset.rotation_mode or 'XYZ'
    _apply_delta(camera, matrix_from_flat(preset.delta_matrix))

    target_location, target_quat, target_scale = matrix_from_flat(
        preset.matrix_basis
    ).decompose()
    start_location, start_quat, start_scale = camera.matrix_basis.decompose()

    _smooth_state = {
        "camera": camera,
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

    camera = state["camera"]
    if camera is None or camera.name not in bpy.data.objects:
        stop_smooth()
        return None

    elapsed = time.perf_counter() - state["started"]
    progress = min(1.0, elapsed / state["duration"])
    eased = progress * progress * (3.0 - 2.0 * progress)  # smoothstep

    try:
        location = state["location"][0].lerp(state["location"][1], eased)
        rotation = state["rotation"][0].slerp(state["rotation"][1], eased)
        scale = state["scale"][0].lerp(state["scale"][1], eased)
        camera.matrix_basis = Matrix.LocRotScale(location, rotation, scale)
    except (ReferenceError, RuntimeError, ValueError):
        stop_smooth()
        return None

    if progress >= 1.0:
        stop_smooth()
        return None
    return 1.0 / 60.0


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


def clamp_index(scene):
    presets = scene.cam_presets
    index = scene.cam_presets_index
    if not presets:
        scene.cam_presets_index = 0
    elif index >= len(presets):
        scene.cam_presets_index = len(presets) - 1
    elif index < 0:
        scene.cam_presets_index = 0
    return scene.cam_presets_index


def reorder_presets(scene, from_index, to_index):
    """Move a preset inside the collection. Returns the new index."""
    presets = scene.cam_presets
    count = len(presets)
    if count < 2:
        return scene.cam_presets_index
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
