"""Headless smoke and regression tests for Camera Preset Manager.

The preset library lives in the add-on preferences, so the suite installs the
built package into the current profile and tests the real extension module.

Run with an isolated profile (tests\\run_tests.bat does this):

    set "BLENDER_USER_RESOURCES=%TEMP%\\cpm_tests"
    blender --background --factory-startup --python tests/run_tests.py

Exits with code 0 when every check passes, 1 otherwise.
"""

import glob
import json
import math
import os
import subprocess
import sys
import tempfile

import bpy
from mathutils import Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCE = os.path.join(ROOT, "camera_preset_manager")
DIST = os.path.join(ROOT, "dist")
MODULE = "bl_ext.user_default.camera_preset_manager"

FAILURES = []
TOLERANCE = 1e-5
CHECKS = [0]
UTILS = None


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


# ---------------------------------------------------------------------------
# build + install
# ---------------------------------------------------------------------------

def build_package():
    print("[build]")
    os.makedirs(DIST, exist_ok=True)
    result = subprocess.run(
        [
            bpy.app.binary_path,
            "--command",
            "extension",
            "build",
            "--source-dir",
            SOURCE,
            "--output-dir",
            DIST,
        ],
        capture_output=True,
        text=True,
    )
    check(result.returncode == 0, "extension build succeeded")
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
    return sorted(glob.glob(os.path.join(DIST, "*.zip")))


def install_package():
    print("[install]")
    packages = build_package()
    if not packages:
        return None
    package = packages[-1]
    print("  using : {}".format(os.path.basename(package)))
    try:
        result = bpy.ops.extensions.package_install_files(
            filepath=package,
            repo="user_default",
            enable_on_install=True,
            overwrite=True,
        )
    except RuntimeError as error:
        check(False, "install failed: {}".format(error))
        return None
    check(result == {'FINISHED'}, "package installed and enabled")
    check(MODULE in sys.modules, "extension module importable")
    return sys.modules.get(MODULE)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def fcurves(action):
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
    # read_factory_settings() also resets preferences and disables the extension,
    # so load an empty home file instead.
    bpy.ops.wm.read_homefile(use_empty=True)
    return bpy.context.scene


def make_camera(scene, name="TestCamera"):
    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def prefs():
    return UTILS.storage(bpy.context)


def library_size():
    store = prefs()
    return len(store.presets) if store is not None else -1


def clear_library():
    store = prefs()
    presets = store.presets
    for index in range(len(presets) - 1, -1, -1):
        presets.remove(index)
    store.presets_index = 0


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_storage():
    print("[storage]")
    store = prefs()
    check(store is not None, "storage resolves to the add-on preferences")
    check(
        hasattr(store, "presets") and hasattr(store, "presets_index"),
        "library is stored on the preferences",
    )

    clear_library()
    added = UTILS.seed_defaults(store)
    check(added == 2, "two factory presets are seeded ({})".format(added))
    names = [preset.name for preset in store.presets]
    check(names == ["Wide", "Close-up"], "factory preset names: {}".format(names))
    check(
        all(len(tuple(preset.matrix_basis)) == 16 for preset in store.presets),
        "factory presets carry full matrices",
    )
    check(
        len(bpy.context.scene.cam_presets) == 0,
        "nothing is written to the legacy per-scene collection",
    )


def test_ui_registration():
    print("[ui registration]")
    panel = getattr(bpy.types, "CAMPRESET_PT_panel", None)
    check(panel is not None, "panel class registered")
    if panel is not None:
        check(getattr(panel, "bl_space_type", None) == 'VIEW_3D', "panel in 3D View")
        check(getattr(panel, "bl_region_type", None) == 'UI', "panel in the sidebar")
        check(
            getattr(panel, "bl_category", None) == "Camera Presets",
            "panel has its own tab",
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
        "restore_defaults",
        "export",
        "load",
    ):
        check(hasattr(bpy.ops.cam_preset, name), "cam_preset.{} is callable".format(name))


def test_icons():
    print("[icons]")
    import re

    icon_property = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon']
    available = {item.identifier for item in icon_property.enum_items}

    used = {}
    for name in sorted(os.listdir(SOURCE)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(SOURCE, name), "r", encoding="utf-8") as handle:
            for icon in re.findall(r"icon\s*=\s*['\"]([A-Za-z0-9_]+)['\"]", handle.read()):
                used.setdefault(icon, name)

    missing = {icon: name for icon, name in used.items() if icon not in available}
    check(not missing, "all {} icon names exist: {}".format(len(used), missing or "ok"))


def test_keymaps():
    print("[keymaps]")
    window_manager = bpy.context.window_manager
    if window_manager is None or window_manager.keyconfigs.addon is None:
        print("  skip  : no addon keyconfig in this session")
        return

    UTILS.get_prefs().register_keymaps = True
    keymap = window_manager.keyconfigs.addon.keymaps.get("3D View")
    check(keymap is not None and len(keymap.keymap_items) >= 2, "hotkeys registered")

    UTILS.get_prefs().register_keymaps = False
    keymap = window_manager.keyconfigs.addon.keymaps.get("3D View")
    check(
        keymap is None or len(keymap.keymap_items) == 0,
        "hotkeys removed when disabled",
    )
    UTILS.get_prefs().register_keymaps = True


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

    check(bpy.ops.cam_preset.save() == {'FINISHED'}, "save finishes")
    check(library_size() >= 1, "preset stored in the library")
    index = prefs().presets_index
    check(
        prefs().presets[index].camera_name == camera.name,
        "preset remembers its camera",
    )

    camera.location = (0.0, 0.0, 0.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera.data.lens = 24.0
    camera.data.dof.use_dof = False
    camera.data.dof.aperture_fstop = 16.0
    camera.data.shift_x = 0.0

    check(bpy.ops.cam_preset.apply(preset_index=index) == {'FINISHED'}, "apply finishes")
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
    index = prefs().presets_index

    camera.location = (0.0, 0.0, 0.0)
    camera.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), 0.0)
    camera.rotation_mode = 'XYZ'

    bpy.ops.cam_preset.apply(preset_index=index)
    check(camera.rotation_mode == 'QUATERNION', "rotation mode restored to quaternion")
    expected = Quaternion((1.0, 0.5, 0.0), math.radians(37.0))
    actual = camera.matrix_basis.to_quaternion()
    check_close(
        actual.rotation_difference(expected).angle, 0.0, "quaternion rotation restored"
    )


def test_orthographic(scene):
    print("[orthographic]")
    camera = scene.camera
    camera.rotation_mode = 'XYZ'
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 12.5
    camera.data.lens = 50.0

    bpy.ops.cam_preset.save()
    index = prefs().presets_index

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
    index = prefs().presets_index
    check(prefs().presets[index].has_focus_object is True, "focus object flag stored")

    camera.data.dof.focus_object = None
    bpy.ops.cam_preset.apply(preset_index=index)
    check(camera.data.dof.focus_object == target, "focus object restored")

    # A library is shared across files: a missing object must not destroy the
    # current focus target.
    keeper = bpy.data.objects.new("Keeper", None)
    scene.collection.objects.link(keeper)
    camera.data.dof.focus_object = keeper
    prefs().presets[index].focus_object_name = "MissingObject"
    result = bpy.ops.cam_preset.apply(preset_index=index)
    check(result == {'FINISHED'}, "apply survives a missing focus object")
    check(
        camera.data.dof.focus_object == keeper,
        "missing focus object keeps the current target",
    )


def test_controller_rig(scene):
    print("[controller rig]")
    camera = scene.camera
    camera.parent = None
    camera.location = (0.0, 0.0, 0.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    for constraint in list(camera.constraints):
        camera.constraints.remove(constraint)

    # Reality check: camera parented to an empty and aimed by a constraint, so
    # its own transform is overridden and only the rig can move it.
    rig = bpy.data.objects.new("CamRig", None)
    scene.collection.objects.link(rig)
    camera.parent = rig
    camera.location = (0.0, -2.0, 0.5)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    track = camera.constraints.new('DAMPED_TRACK')
    track.target = rig
    track.track_axis = 'TRACK_NEGATIVE_Z'
    scene.cam_presets_controller = rig

    rig.location = (5.0, -5.0, 2.0)
    bpy.context.view_layer.update()
    bpy.ops.cam_preset.save()
    index = prefs().presets_index
    preset = prefs().presets[index]
    check(preset.controller_name == "CamRig", "preset stores the rig object")
    check(len(tuple(preset.controller_matrix)) == 16, "preset stores the rig transform")

    rig.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    check(bpy.ops.cam_preset.apply(preset_index=index) == {'FINISHED'}, "apply finishes")
    bpy.context.view_layer.update()

    check_vector(rig.location, (5.0, -5.0, 2.0), "rig transform restored")
    world = camera.matrix_world.translation
    check_vector(world, (5.0, -7.0, 2.5), "camera follows the rig after apply")

    # The constraint owns the camera rotation: the view direction must still
    # point at the rig after the preset is applied.
    forward = -camera.matrix_world.col[2].xyz.normalized()
    to_rig = (rig.matrix_world.translation - world).normalized()
    check(forward.dot(to_rig) > 0.99, "constraint keeps the camera aimed at the rig")

    for constraint in list(camera.constraints):
        camera.constraints.remove(constraint)
    camera.parent = None
    scene.cam_presets_controller = None


def test_index_bounds(scene):
    print("[index bounds]")
    check(
        bpy.ops.cam_preset.apply(preset_index=999) == {'CANCELLED'},
        "explicit out-of-range index is rejected",
    )
    previous = prefs().presets_index
    prefs().presets_index = 999
    check(
        bpy.ops.cam_preset.apply(preset_index=-1) == {'CANCELLED'},
        "invalid active index is rejected",
    )
    prefs().presets_index = previous


def test_partial_channels(scene):
    print("[partial channels]")
    camera = scene.camera
    camera.location = (7.0, 8.0, 9.0)
    bpy.ops.cam_preset.save()
    index = prefs().presets_index

    saved_location = tuple(camera.location)
    saved_lens = prefs().presets[index].lens

    camera.location = (0.0, 0.0, 0.0)
    camera.data.lens = 18.0

    scene.cam_presets_channels = 'OPTICS'
    bpy.ops.cam_preset.apply(preset_index=index)
    check_vector(camera.location, (0.0, 0.0, 0.0), "optics-only keeps the transform")
    check_close(camera.data.lens, saved_lens, "optics-only applies the lens")

    scene.cam_presets_channels = 'TRANSFORM'
    bpy.ops.cam_preset.apply(preset_index=index)
    check_vector(camera.location, saved_location, "transform-only restores transform")
    check_close(camera.data.lens, saved_lens, "transform-only keeps lens")
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
    bpy.ops.cam_preset.apply(preset_index=prefs().presets_index)
    scene.cam_presets_keyframe = False

    animation = camera.animation_data
    action = animation.action if animation else None
    check(action is not None, "applying with keyframe creates animation data")
    if action is not None:
        check(action.frame_range[1] >= 10.0, "keyframe placed at the current frame")
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


def test_smooth(scene):
    print("[smooth]")
    camera = scene.camera
    camera.parent = None
    scene.frame_set(1)

    camera.location = (0.0, 0.0, 0.0)
    bpy.ops.cam_preset.save()
    index = prefs().presets_index
    target = tuple(prefs().presets[index].matrix_basis)
    target_x = target[3]

    camera.location = (-4.0, 0.0, 0.0)
    UTILS.start_smooth(camera, prefs().presets[index], controller=None)
    check(UTILS.is_smoothing(), "smooth transition starts")

    state = UTILS._smooth_state
    state["started"] = state["started"] - state["duration"] - 1.0
    UTILS._smooth_tick()
    check(not UTILS.is_smoothing(), "smooth transition completes")
    check_close(camera.location.x, target_x, "smooth transition lands on the preset")

    # Mid-flight interpolation must stay between the endpoints.
    camera.location = (-4.0, 0.0, 0.0)
    UTILS.start_smooth(camera, prefs().presets[index], controller=None)
    state = UTILS._smooth_state
    state["started"] = state["started"] - state["duration"] * 0.5
    UTILS._smooth_tick()
    value = camera.location.x
    check(-4.0 < value < target_x, "smooth interpolates between endpoints")
    UTILS.stop_smooth()
    bpy.context.view_layer.update()


def test_duplicate_and_move(scene):
    print("[list management]")
    before = library_size()
    bpy.ops.cam_preset.duplicate()
    check(library_size() == before + 1, "duplicate adds a preset")
    names = [preset.name for preset in prefs().presets]
    check(len(set(names)) == len(names), "preset names stay unique")

    index = prefs().presets_index
    bpy.ops.cam_preset.move(direction='UP')
    check(prefs().presets_index == index - 1, "move up changes the index")
    bpy.ops.cam_preset.move(direction='DOWN')
    check(prefs().presets_index == index, "move down restores the index")

    prefs().presets_index = 0
    count = library_size()
    bpy.ops.cam_preset.delete()
    check(library_size() == count - 1, "delete removes a preset")
    check(
        0 <= prefs().presets_index < max(1, library_size()),
        "active index stays inside the list",
    )


def test_json_roundtrip(scene):
    print("[json]")
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "presets.json")

    exported = library_size()
    check(bpy.ops.cam_preset.export(filepath=path) == {'FINISHED'}, "export finishes")
    check(os.path.exists(path), "export writes the file")

    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    check(payload.get("schema") == 1, "exported schema version")
    check(len(payload.get("presets", [])) == exported, "exported every preset")

    snapshot = [
        {"name": preset.name, "lens": preset.lens, "use_dof": preset.use_dof}
        for preset in prefs().presets
    ]

    clear_library()
    check(library_size() == 0, "library cleared")

    check(bpy.ops.cam_preset.load(filepath=path) == {'FINISHED'}, "load finishes")
    check(library_size() == exported, "load restored the count")
    check(
        [item["name"] for item in snapshot]
        == [preset.name for preset in prefs().presets],
        "loaded names match the source exactly",
    )
    restored = {
        preset.name: (preset.lens, preset.use_dof) for preset in prefs().presets
    }
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
    clear_library()
    bpy.ops.cam_preset.apply(preset_index=0)
    check(library_size() == 0, "apply on an empty library is a no-op")
    check(
        bpy.ops.cam_preset.save() == {'CANCELLED'},
        "save without a camera is cancelled",
    )


def test_partial_install():
    print("[partial install]")
    module = sys.modules[MODULE]
    util = module.utils
    saved = getattr(util, "bootstrap", None)
    try:
        module.unregister()
        delattr(util, "bootstrap")
        try:
            module.register()
            registered = True
        except Exception as error:  # noqa: BLE001
            registered = False
            print("  error : {}".format(error))
        check(registered, "register survives a stale utils module")

        window_manager = bpy.context.window_manager
        if window_manager is not None and window_manager.keyconfigs.addon is not None:
            keymap = window_manager.keyconfigs.addon.keymaps.get("3D View")
            check(
                keymap is not None and len(keymap.keymap_items) >= 2,
                "hotkeys still registered with a stale utils module",
            )
    finally:
        try:
            module.unregister()
        except Exception:  # noqa: BLE001
            pass
        setattr(util, "bootstrap", saved)
        module.register()


def test_reload():
    print("[reload]")
    module = sys.modules[MODULE]
    module.unregister()
    check(not hasattr(bpy.types.Scene, "cam_presets_channels"), "scene props removed")
    module.register()
    check(hasattr(bpy.types.Scene, "cam_presets_channels"), "scene props restored")
    check(library_size() >= 0, "library survives an add-on reload")


def main():
    global UTILS

    if not os.environ.get("BLENDER_USER_RESOURCES"):
        print(
            "BLENDER_USER_RESOURCES is not set: refusing to install into the real profile.\n"
            "Use tests\\run_tests.bat or set it to a temporary directory."
        )
        raise SystemExit(2)

    module = install_package()
    if module is None:
        raise SystemExit(1)
    UTILS = module.utils

    test_storage()
    test_ui_registration()
    test_icons()
    test_keymaps()

    scene = fresh_scene()
    test_roundtrip(scene)
    test_quaternion(scene)
    test_orthographic(scene)
    test_focus_object(scene)
    test_controller_rig(scene)
    test_index_bounds(scene)
    test_partial_channels(scene)
    test_keyframe(scene)
    test_smooth(scene)
    test_duplicate_and_move(scene)
    test_json_roundtrip(scene)
    test_empty_scene()
    test_partial_install()
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
