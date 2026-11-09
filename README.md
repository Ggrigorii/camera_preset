# Camera Preset Manager

Blender 4.2+ extension that stores complete camera states (transform, optics, depth of
field) and switches between them from one pie menu.

## Camera rig

Presets drive the **rig object**, not the camera transform, because constraints override
it. Typical setup:

```
Empty "CameraRig"        <- position of the shot
   └── Camera            <- Child Of / parent + Damped Track or Track To
```

Required constraint settings for a camera:

| Parameter | Value |
|---|---|
| Track Axis | `-Z` |
| Up | `Y` |
| Target | the rig empty |

`Damped Track` defaults to `TRACK_Y`, which is wrong for a camera — set the axis manually.
Then pick the empty in the panel field **Rig**. Without it, applying a preset on a
constrained camera changes nothing and the panel warns about it.

## Features

- Save / update / duplicate / reorder / delete camera presets
- Pie menu on a single hotkey, shows the live preset list
- Full state fidelity: `matrix_basis` + rotation mode, sensor size, ortho scale, lens shift, DOF focus object
- Rig support: transform goes to the controller empty, optics and DOF to the camera
- Partial apply: transform only, optics only, DOF only
- Keyframe mode: apply a preset into a camera animation instead of hard-setting values
- Smooth transition (transform) with configurable duration and forced viewport redraw
- Global library: one preset list for every window and every `.blend`, stored in the
  add-on preferences; JSON export / load for sharing
- Two factory presets (`Wide`, `Close-up`) seeded on first run, restorable via `Defaults`
- Warnings when animation, drivers or constraints will override the preset

## Install

```bat
blender --command extension build --source-dir camera_preset_manager --output-dir dist
```

Then `Edit > Preferences > Get Extensions > Install from Disk` and pick the `.zip`
from `dist`.

For development, add this repository to Blender's scripts path or enable the folder as
an extension with `blender --command extension` tooling.

## Hotkeys

| Keys | Action |
|---|---|
| `Ctrl+Alt+C` | Pie menu |
| `Ctrl+Alt+S` | Save new preset |

Both are registered in the add-on keymap and can be rebound in
`Edit > Preferences > Keymap > 3D View`. They can also be disabled entirely in the
add-on preferences; the panel shows any detected conflicts.

## Tests

Static checks (no Blender needed):

```bat
python tests\static_check.py
```

Headless behaviour tests (builds, installs into an isolated profile, 89 checks):

```bat
tests\run_tests.bat "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

Install verification against an isolated profile (does not touch your settings):

```bat
set "BLENDER_USER_RESOURCES=%TEMP%\cpm_profile"
mkdir "%TEMP%\cpm_profile\extensions"
blender --background --factory-startup --python tests\install_check.py
```

Regenerate the factory presets (needs Blender for the look-at matrices):

```bat
blender --background --factory-startup --python tests\make_defaults.py
```

## Layout

```
camera_preset_manager/   extension package (manifest + modules)
tests/                   static check, headless suite, build helpers
SPEC.md                  full technical specification (v1.1)
```

`SPEC.md` is the source of truth for behaviour, constraints and the Definition of Done.
