"""Headless smoke and regression tests for Camera Preset Manager.

Run with:
    blender --background --factory-startup --python tests/run_tests.py

Exits with code 0 when every check passes, 1 otherwise.
"""

import json
import math
import os
import sys
import tempfile

import bpy
from mathutils import Quaternion

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import camera_preset_manager as cpm  # noqa: E402

FAILURES = []
TOLERANCE = 1e-5
CHECKS = [0]


def check(condition, message):
    CHECKS[0] += 1
    if condition:
        print("  ok    : " + message)
    else:
        FAILURES.append(message)
        print("  FAILED: " + message)


def check_close(value, expected, message, tolerance=TOLERANCE):
    check(
        abs(value - expected) <= tolerance,
        "{} ({:.6f} ~ {:.6f})".format(message, value, expected),
    )


def check_vector(value, expected, message):
    ok = all(abs(a - b) <= TOLERANCE for a, b in zip(tuple(value), tuple(expected)))
    check(ok, message)


def fcurves(action):
    """Return F-curves for both legacy and slotted (4.4+) actions."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        try:
            return list(legacy)
        except (AttributeError, TypeError):
            pass
    curves = []
    try:
        for layer in getattr(action, "layers", []):
            for strip in layer.strips:
                for slot in action.slots:
                    bag = strip.channelbag(slot)
                    if bag is not None:
                        curves.extend(bag.fcurves)
    except (AttributeError, TypeError):
        pass
    return curves


def fresh_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def test_ui_registration():
    print("[ui registration]")
    panel = getattr(bpy.types, "CAMPRESET_PT_panel", None)
    check(panel is not None, "panel class registered")
    if panel is not None:
        check(
            getattr(panel, "bl_space_type", None) == 'VIEW_3D',
            "panel lives in the 3D View",
        )
        check(
            getattr(panel, "bl_region_type", None) == 'UI',
            "panel lives in the sidebar",
        )
        check(
            getattr(panel, "bl_category", None) == "Camera Presets",
            "panel has its own sidebar tab",
        )

    for name in ("CAMPRESET_MT_pie", "CAMPRESET_MT_list", "CAMPRESET_UL_list"):
        check(getattr(bpy.types, name, None) is not None, "{} registered".format(name))

    for name in (
        "save",
        "update",
        "apply",
        "delete",
        "duplicate",
        "move",
        "reset_scene",
        "export",
        "load",
    ):
        check(
            hasattr(bpy.ops.cam_preset, name),
            "operator cam_preset.{} is callable".format(name),
        )


def test_icons():
    print("[icons]")
    import re

    icon_property = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon']
    available = {item.identifier for item in icon_property.enum_items}

    used = {}
    for name in sorted(os.listdir(os.path.join(ROOT, "camera_preset_manager"))):
        if not name.endswith(".py"):
            continue
        path = os.path.join(ROOT, "camera_preset_manager", name)
        with open(path, "r", encoding="utf-8") as handle:
            for icon in re.findall(r"icon\s*=\s*['\"]([A-Za-z0-9_]+)['\"]", handle.read()):
                used.setdefault(icon, name)

    missing = {icon: name for icon, name in used.items() if icon not in available}
    check(
        not missing,
        "all {} icon names exist: {}".format(len(used), missing or "ok"),
    )


def make_camera(scene, name="TestCamera"):
    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def test_registration():
    print("[registration]")
    try:
        cpm.unregister()
    except Exception:  # noqa: BLE001 - first run has nothing to unregister
        pass
    cpm.register()
    check(hasattr(bpy.types.Scene, "cam_presets"), "scene stores presets")
    check(hasattr(bpy.types.Scene, "cam_presets_index"), "scene stores active index")
    check(
        bpy.types.Scene.bl_rna.properties.get("cam_presets") is not None,
        "cam_presets is registered in RNA",
    )

    window_manager = bpy.context.window_manager
    if window_manager is None or window_manager.keyconfigs.addon is None:
        print("  skip  : keymaps (no window manager in background mode)")
        return
    cpm.keymaps.unregister()
    cpm.keymaps.register(True)
    keymap = window_manager.keyconfigs.addon.keymaps.get("3D View")
    check(
        keymap is not None and len(keymap.keymap_items) >= 2,
        "hotkeys registered in the addon keyconfig",
    )
    cpm.keymaps.unregister()
    keymap = window_manager.keyconfigs.addon.keymaps.get("3D View")
    check(
        keymap is None or len(keymap.keymap_items) == 0,
        "hotkeys removed on unregister",
    )


def test_roundtrip(scene):
    print("[roundtrip]")
    camera = make_camera(scene)

    camera.location = (1.0, 2.0, 3.0)
    camera.rotation_euler = (0.1, 0.2, 0.3)
    camera.data.lens = 85.0
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 2.8
    camera.data.dof.focus_distance = 5.0
    camera.data.sensor_width = 36.0
    camera.data.shift_x = 0.05

    result = bpy.ops.cam_preset.save()
    check(result == {'FINISHED'}, "save finishes")
    check(len(scene.cam_presets) == 1, "preset stored")
    check(scene.cam_presets_index == 0, "new preset becomes active")
    check(
        scene.cam_presets[0].camera_name == camera.name,
        "preset remembers its camera",
    )

    camera.location = (0.0, 0.0, 0.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera.data.lens = 24.0
    camera.data.dof.use_dof = False
    camera.data.dof.aperture_fstop = 16.0
    camera.data.shift_x = 0.0

    result = bpy.ops.cam_preset.apply(preset_index=0)
    check(result == {'FINISHED'}, "apply finishes")

    check_vector(camera.location, (1.0, 2.0, 3.0), "location restored")
    check_vector(camera.rotation_euler, (0.1, 0.2, 0.3), "euler rotation restored")
    check_close(camera.data.lens, 85.0, "lens restored")
    check(camera.data.dof.use_dof is True, "depth of field restored")
    check_close(camera.data.dof.aperture_fstop, 2.8, "f-stop restored")
    check_close(camera.data.dof.focus_distance, 5.0, "focus distance restored")
    check_close(camera.data.shift_x, 0.05, "lens shift restored")


def test_quaternion(scene):
    print("[quaternion]")
    camera = scene.camera
    camera.rotation_mode = 'QUATERNION'
    camera.rotation_quaternion = Quaternion((1.0, 0.5, 0.0), math.radians(37.0))
    camera.location = (4.0, 5.0, 6.0)
    camera.data.lens = 50.0

    bpy.ops.cam_preset.save()
    index = scene.cam_presets_index

    camera.location = (0.0, 0.0, 0.0)
    camera.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), 0.0)
    camera.rotation_mode = 'XYZ'

    bpy.ops.cam_preset.apply(preset_index=index)
    check(camera.rotation_mode == 'QUATERNION', "rotation mode restored to quaternion")
    expected = Quaternion((1.0, 0.5, 0.0), math.radians(37.0))
    actual = camera.matrix_basis.to_quaternion()
    check_close(
        actual.rotation_difference(expected).angle,
        0.0,
        "quaternion rotation restored",
    )


def test_orthographic(scene):
    print("[orthographic]")
    camera = scene.camera
    camera.rotation_mode = 'XYZ'
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 12.5
    camera.data.lens = 50.0

    bpy.ops.cam_preset.save()
    index = scene.cam_presets_index

    camera.data.type = 'PERSP'
    camera.data.ortho_scale = 1.0
    bpy.ops.cam_preset.apply(preset_index=index)

    check(camera.data.type == 'ORTHO', "orthographic type restored")
    check_close(camera.data.ortho_scale, 12.5, "ortho scale restored")
    check_close(camera.data.lens, 50.0, "lens restored alongside ortho")


def test_focus_object(scene):
    print("[focus object]")
    camera = scene.camera
    camera.data.type = 'PERSP'

    target = bpy.data.objects.new("FocusTarget", None)
    scene.collection.objects.link(target)

    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = target
    camera.data.dof.focus_distance = 3.0

    bpy.ops.cam_preset.save()
    index = scene.cam_presets_index

    camera.data.dof.focus_object = None
    bpy.ops.cam_preset.apply(preset_index=index)
    check(camera.data.dof.focus_object == target, "focus object restored")

    target.name = "FocusTargetRenamed"
    scene.cam_presets[index].focus_object_name = "MissingObject"
    result = bpy.ops.cam_preset.apply(preset_index=index)
    check(result == {'FINISHED'}, "apply survives a missing focus object")
    check(
        camera.data.dof.focus_object is None,
        "missing focus object falls back to focus distance",
    )


def test_index_bounds(scene):
    print("[index bounds]")
    result = bpy.ops.cam_preset.apply(preset_index=999)
    check(result == {'CANCELLED'}, "explicit out-of-range index is rejected")

    previous = scene.cam_presets_index
    scene.cam_presets_index = 999
    result = bpy.ops.cam_preset.apply(preset_index=-1)
    check(result == {'CANCELLED'}, "invalid active index is rejected")
    scene.cam_presets_index = previous


def test_partial_channels(scene):
    print("[partial channels]")
    camera = scene.camera
    camera.location = (7.0, 8.0, 9.0)
    bpy.ops.cam_preset.save()
    index = scene.cam_presets_index

    saved_location = tuple(camera.location)
    saved_lens = scene.cam_presets[index].lens

    camera.location = (0.0, 0.0, 0.0)
    camera.data.lens = 18.0

    scene.cam_presets_channels = 'OPTICS'
    bpy.ops.cam_preset.apply(preset_index=index)
    check_vector(
        camera.location, (0.0, 0.0, 0.0), "optics-only leaves the transform alone"
    )
    check_close(camera.data.lens, saved_lens, "optics-only applies the lens")

    scene.cam_presets_channels = 'TRANSFORM'
    bpy.ops.cam_preset.apply(preset_index=index)
    check_vector(camera.location, saved_location, "transform-only restores transform")
    check_close(camera.data.lens, saved_lens, "transform-only leaves lens alone")
    scene.cam_presets_channels = 'ALL'


def test_keyframe(scene):
    print("[keyframe]")
    camera = scene.camera
    scene.cam_presets_channels = 'ALL'

    scene.frame_set(1)
    camera.location = (0.0, 0.0, 0.0)
    camera.keyframe_insert("location", frame=1)

    scene.frame_set(10)
    scene.cam_presets_keyframe = True
    bpy.ops.cam_preset.apply(preset_index=scene.cam_presets_index)
    scene.cam_presets_keyframe = False

    animation = camera.animation_data
    action = animation.action if animation else None
    check(action is not None, "applying with keyframe creates animation data")

    if action is not None:
        start, end = action.frame_range
        check(end >= 10.0, "new keyframe is placed at the current frame")
        curves = fcurves(action)
        if curves:
            location_curve = next(
                (item for item in curves if item.data_path == "location"), None
            )
            check(location_curve is not None, "location F-curve exists")
            if location_curve is not None:
                check(
                    len(location_curve.keyframe_points) >= 2,
                    "existing animation kept alongside the new keyframe",
                )


def test_duplicate_and_move(scene):
    print("[list management]")
    before = len(scene.cam_presets)
    bpy.ops.cam_preset.duplicate()
    check(len(scene.cam_presets) == before + 1, "duplicate adds a preset")
    names = [preset.name for preset in scene.cam_presets]
    check(len(set(names)) == len(names), "preset names stay unique")

    index = scene.cam_presets_index
    bpy.ops.cam_preset.move(direction='UP')
    check(scene.cam_presets_index >= 0, "move up keeps a valid index")
    bpy.ops.cam_preset.move(direction='DOWN')
    check(scene.cam_presets_index == index, "move down restores the index")

    scene.cam_presets_index = 0
    count = len(scene.cam_presets)
    bpy.ops.cam_preset.delete()
    check(len(scene.cam_presets) == count - 1, "delete removes a preset")
    check(
        0 <= scene.cam_presets_index < max(1, len(scene.cam_presets)),
        "active index stays inside the list",
    )


def test_json_roundtrip(scene):
    print("[json]")
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "presets.json")

    exported = len(scene.cam_presets)
    result = bpy.ops.cam_preset.export(filepath=path)
    check(result == {'FINISHED'}, "export finishes")
    check(os.path.exists(path), "export writes the file")

    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    check(payload.get("schema") == 1, "exported schema version")
    check(len(payload.get("presets", [])) == exported, "exported every preset")

    snapshot = [
        {"name": preset.name, "lens": preset.lens, "use_dof": preset.use_dof}
        for preset in scene.cam_presets
    ]

    bpy.ops.cam_preset.reset_scene()
    check(len(scene.cam_presets) == 0, "reset clears the list")

    result = bpy.ops.cam_preset.load(filepath=path)
    check(result == {'FINISHED'}, "load finishes")
    check(len(scene.cam_presets) == exported, "load restored the count")
    restored = {
        preset.name: (preset.lens, preset.use_dof) for preset in scene.cam_presets
    }
    check(
        [item["name"] for item in snapshot] == [preset.name for preset in scene.cam_presets],
        "loaded names match the source exactly",
    )
    check(
        all(
            item["name"] in restored
            and abs(restored[item["name"]][0] - item["lens"]) <= TOLERANCE
            and restored[item["name"]][1] == item["use_dof"]
            for item in snapshot
        ),
        "loaded values match the source",
    )


def test_empty_scene():
    print("[empty scene]")
    scene = fresh_scene()
    bpy.ops.cam_preset.apply(preset_index=0)
    check(len(scene.cam_presets) == 0, "apply on an empty scene is a no-op")
    result = bpy.ops.cam_preset.save()
    check(result == {'CANCELLED'}, "save without a camera is cancelled")


def test_reload():
    print("[reload]")
    cpm.unregister()
    check(not hasattr(bpy.types.Scene, "cam_presets"), "scene properties removed")
    cpm.register()
    check(hasattr(bpy.types.Scene, "cam_presets"), "scene properties restored")
    cpm.unregister()


def main():
    test_registration()
    test_ui_registration()
    test_icons()
    scene = fresh_scene()
    test_roundtrip(scene)
    test_quaternion(scene)
    test_orthographic(scene)
    test_focus_object(scene)
    test_index_bounds(scene)
    test_partial_channels(scene)
    test_keyframe(scene)
    test_duplicate_and_move(scene)
    test_json_roundtrip(scene)
    test_empty_scene()
    test_reload()

    print()
    if FAILURES:
        print("FAILED: {} of {} check(s)".format(len(FAILURES), CHECKS[0]))
        for message in FAILURES:
            print("  - " + message)
        raise SystemExit(1)
    print("All {} checks passed.".format(CHECKS[0]))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
