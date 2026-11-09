"""Verify that the built package installs and works as a real extension.

Run against an isolated profile so the user's Blender setup is untouched:

    set BLENDER_USER_RESOURCES=<temp dir>
    blender --background --factory-startup --python tests/install_check.py
"""

import glob
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
MODULE = "bl_ext.user_default.camera_preset_manager"

FAILURES = []
CHECKS = [0]


def check(condition, message):
    CHECKS[0] += 1
    if condition:
        print("  ok    : " + message)
    else:
        FAILURES.append(message)
        print("  FAILED: " + message)


def main():
    print("[install]")
    packages = sorted(glob.glob(os.path.join(DIST, "*.zip")))
    check(bool(packages), "package found in {}".format(DIST))
    if not packages:
        raise SystemExit(1)
    package = packages[-1]
    print("  using : {}".format(package))

    result = bpy.ops.extensions.package_install_files(
        filepath=package,
        repo="user_default",
        enable_on_install=True,
        overwrite=True,
    )
    check(result == {'FINISHED'}, "package_install_files finished")

    addons = set(bpy.context.preferences.addons.keys())
    check(MODULE in addons, "extension enabled as {}".format(MODULE))
    check(MODULE in sys.modules, "extension module is importable")

    module = sys.modules.get(MODULE)
    if module is None:
        raise SystemExit(1)

    print("[preferences]")
    addon = bpy.context.preferences.addons.get(MODULE)
    check(addon is not None, "add-on entry present in preferences")
    prefs = addon.preferences if addon is not None else None
    check(prefs is not None, "AddonPreferences instance resolves")
    if prefs is not None:
        # Instance ``bl_idname`` is not a usable string for AddonPreferences;
        # the class attribute is authoritative.
        check(
            getattr(type(prefs), "bl_idname", None) == MODULE,
            "preferences class bl_idname matches the extension module",
        )
        check(
            module.utils.get_prefs() == prefs,
            "utils.get_prefs() finds the preferences under the extension name",
        )
        check(prefs.register_keymaps is True, "hotkeys enabled by default")
        check(prefs.retarget_mode == 'SCENE', "default retarget mode is the scene camera")

    print("[ui]")
    for name in ("CAMPRESET_PT_panel", "CAMPRESET_MT_pie", "CAMPRESET_UL_list"):
        check(getattr(bpy.types, name, None) is not None, "{} registered".format(name))

    print("[runtime]")
    check(hasattr(bpy.types.Scene, "cam_presets"), "scene properties registered")

    scene = bpy.context.scene
    data = bpy.data.cameras.new("InstalledCam")
    camera = bpy.data.objects.new("InstalledCam", data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    camera.location = (2.0, 3.0, 4.0)
    data.lens = 135.0

    check(bpy.ops.cam_preset.save() == {'FINISHED'}, "save works from the installed package")
    # The library also holds the factory presets, so use the active index.
    index = prefs.presets_index
    camera.location = (0.0, 0.0, 0.0)
    data.lens = 18.0
    check(
        bpy.ops.cam_preset.apply(preset_index=index) == {'FINISHED'},
        "apply works from the installed package",
    )
    check(
        abs(camera.location.x - 2.0) < 1e-5 and abs(data.lens - 135.0) < 1e-5,
        "state restored through the installed package",
    )

    print()
    if FAILURES:
        print("FAILED: {} of {} check(s)".format(len(FAILURES), CHECKS[0]))
        for message in FAILURES:
            print("  - " + message)
        raise SystemExit(1)
    print("All {} install checks passed.".format(CHECKS[0]))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
