"""Property groups and storage declarations for Camera Preset Manager."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

IDENTITY_16 = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)

ROTATION_MODES = [
    ('XYZ', "XYZ Euler", "Euler rotation, X then Y then Z"),
    ('XZY', "XZY Euler", "Euler rotation, X then Z then Y"),
    ('YXZ', "YXZ Euler", "Euler rotation, Y then X then Z"),
    ('YZX', "YZX Euler", "Euler rotation, Y then Z then X"),
    ('ZXY', "ZXY Euler", "Euler rotation, Z then X then Y"),
    ('ZYX', "ZYX Euler", "Euler rotation, Z then Y then X"),
    ('QUATERNION', "Quaternion", "Quaternion rotation"),
    ('AXIS_ANGLE', "Axis Angle", "Axis angle rotation"),
]

CAMERA_TYPES = [
    ('PERSP', "Perspective", "Perspective camera"),
    ('ORTHO', "Orthographic", "Orthographic camera"),
    ('PANO', "Panoramic", "Panoramic camera"),
]

SENSOR_FITS = [
    ('AUTO', "Auto", "Fit to the larger of width or height"),
    ('HORIZONTAL', "Horizontal", "Fit to the sensor width"),
    ('VERTICAL', "Vertical", "Fit to the sensor height"),
]

CHANNELS = [
    ('ALL', "All Channels", "Apply transform, optics and depth of field"),
    ('TRANSFORM', "Transform Only", "Apply location, rotation and scale only"),
    ('OPTICS', "Optics Only", "Apply camera type, lens and sensor only"),
    ('DOF', "Depth of Field Only", "Apply depth of field settings only"),
]

CHANNEL_KEYS = {'ALL', 'TRANSFORM', 'OPTICS', 'DOF'}

# Single source of truth for naming, copying and (de)serialisation.
PRESET_FIELDS = (
    'name',
    'camera_name',
    'controller_name',
    'rotation_mode',
    'matrix_basis',
    'delta_matrix',
    'controller_matrix',
    'camera_type',
    'lens',
    'sensor_width',
    'sensor_height',
    'sensor_fit',
    'shift_x',
    'shift_y',
    'clip_start',
    'clip_end',
    'ortho_scale',
    'panorama_type',
    'use_dof',
    'has_focus_object',
    'focus_distance',
    'aperture_fstop',
    'focus_object_name',
)


class CAMPRESET_PG_preset(PropertyGroup):
    """A single stored camera state."""

    name: StringProperty(name="Name", default="Preset")

    camera_name: StringProperty(
        name="Camera",
        default="",
        description="Camera this preset was captured from",
    )
    controller_name: StringProperty(
        name="Controller",
        default="",
        description="Object driving the camera through constraints (usually an empty)",
    )

    # --- transform: properties of the Object, not of the camera data ---
    rotation_mode: EnumProperty(
        name="Rotation Mode",
        items=ROTATION_MODES,
        default='XYZ',
    )
    matrix_basis: FloatVectorProperty(
        name="Basis Matrix",
        size=16,
        default=IDENTITY_16,
        precision=4,
    )
    delta_matrix: FloatVectorProperty(
        name="Delta Matrix",
        size=16,
        default=IDENTITY_16,
        precision=4,
    )
    controller_matrix: FloatVectorProperty(
        name="Controller Matrix",
        size=16,
        default=IDENTITY_16,
        precision=4,
    )

    # --- optics: properties of the Camera data ---
    camera_type: EnumProperty(
        name="Camera Type",
        items=CAMERA_TYPES,
        default='PERSP',
    )
    lens: FloatProperty(name="Lens", default=50.0, unit='CAMERA')
    sensor_width: FloatProperty(name="Sensor Width", default=36.0)
    sensor_height: FloatProperty(name="Sensor Height", default=24.0)
    sensor_fit: EnumProperty(name="Sensor Fit", items=SENSOR_FITS, default='AUTO')
    shift_x: FloatProperty(name="Shift X", default=0.0)
    shift_y: FloatProperty(name="Shift Y", default=0.0)
    clip_start: FloatProperty(name="Clip Start", default=0.1)
    clip_end: FloatProperty(name="Clip End", default=1000.0)
    ortho_scale: FloatProperty(name="Ortho Scale", default=6.0)
    panorama_type: StringProperty(
        name="Panorama Type",
        default="",
        description="Stored as a string to stay compatible with new panorama types",
    )

    # --- depth of field ---
    use_dof: BoolProperty(name="Use Depth of Field", default=False)
    has_focus_object: BoolProperty(
        name="Has Focus Object",
        default=False,
        description="Whether the camera used a focus object instead of a focus distance",
    )
    focus_distance: FloatProperty(name="Focus Distance", default=10.0, unit='LENGTH')
    aperture_fstop: FloatProperty(name="F-Stop", default=2.8, min=0.0, soft_max=128.0)
    focus_object_name: StringProperty(
        name="Focus Object",
        default="",
        description="Object used as the depth of field focus target",
    )


def register_scene_properties():
    Scene = bpy.types.Scene

    # Storage moved to the add-on preferences (shared by every window and file).
    # The scene collection is kept only so presets saved by 1.1 can be migrated.
    if not hasattr(Scene, "cam_presets"):
        Scene.cam_presets = CollectionProperty(type=CAMPRESET_PG_preset)
    if not hasattr(Scene, "cam_presets_index"):
        Scene.cam_presets_index = IntProperty(
            name="Active Preset (legacy)",
            default=0,
            min=0,
        )
    if not hasattr(Scene, "cam_presets_controller"):
        Scene.cam_presets_controller = PointerProperty(
            type=bpy.types.Object,
            name="Controller",
            description="Object driving the camera through constraints, usually an empty",
        )
    if not hasattr(Scene, "cam_presets_channels"):
        Scene.cam_presets_channels = EnumProperty(
            name="Apply",
            items=CHANNELS,
            default='ALL',
            description="Which channels to apply",
        )
    if not hasattr(Scene, "cam_presets_keyframe"):
        Scene.cam_presets_keyframe = BoolProperty(
            name="Keyframe",
            default=False,
            description="Insert keyframes at the current frame instead of a hard set",
        )
    if not hasattr(Scene, "cam_presets_smooth"):
        Scene.cam_presets_smooth = BoolProperty(
            name="Smooth",
            default=False,
            description="Animate the camera transform to the preset",
        )


def unregister_scene_properties():
    Scene = bpy.types.Scene
    for attribute in (
        "cam_presets",
        "cam_presets_index",
        "cam_presets_controller",
        "cam_presets_channels",
        "cam_presets_keyframe",
        "cam_presets_smooth",
    ):
        if hasattr(Scene, attribute):
            delattr(Scene, attribute)


classes = (CAMPRESET_PG_preset,)
