"""Regenerate camera_preset_manager/defaults.json.

Usage:
    blender --background --factory-startup --python tests/make_defaults.py

Values are deliberately neutral studio framing; replace them with real data by
configuring the rig in Blender and pressing Export in the add-on panel.
"""

import json
import os

from mathutils import Matrix, Vector

PACKAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "camera_preset_manager",
)
OUTPUT = os.path.join(PACKAGE, "defaults.json")

IDENTITY = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]


def flat(matrix):
    return [round(value, 6) for row in matrix for value in row]


def aiming_matrix(location, target):
    direction = Vector(target) - Vector(location)
    rotation = direction.to_track_quat('-Z', 'Y')
    return Matrix.Translation(Vector(location)) @ rotation.to_matrix().to_4x4()


def preset(name, location, target, lens, dof, fstop):
    matrix = aiming_matrix(location, target)
    return {
        "name": name,
        "camera_name": "",
        "controller_name": "",
        "rotation_mode": "XYZ",
        "matrix_basis": flat(matrix),
        "delta_matrix": list(IDENTITY),
        "controller_matrix": list(IDENTITY),
        "camera_type": "PERSP",
        "lens": float(lens),
        "sensor_width": 36.0,
        "sensor_height": 24.0,
        "sensor_fit": "AUTO",
        "shift_x": 0.0,
        "shift_y": 0.0,
        "clip_start": 0.1,
        "clip_end": 1000.0,
        "ortho_scale": 6.0,
        "panorama_type": "",
        "use_dof": bool(dof),
        "has_focus_object": False,
        "focus_distance": round((Vector(target) - Vector(location)).length, 4),
        "aperture_fstop": float(fstop),
        "focus_object_name": "",
    }


def main():
    entries = [
        preset("Wide", (7.0, -7.0, 4.0), (0.0, 0.0, 1.2), 24.0, False, 5.6),
        preset("Close-up", (2.4, -2.4, 1.6), (0.0, 0.0, 1.2), 85.0, True, 2.8),
    ]
    payload = {"schema": 1, "presets": entries}
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print("wrote", OUTPUT, "with", len(entries), "presets")


if __name__ == "__main__":
    main()
