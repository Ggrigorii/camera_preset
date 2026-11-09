# Camera Preset Manager

Blender 4.2+ extension that stores complete camera states (transform, optics, depth of
field) and switches between them from one pie menu.

## Features

- Save / update / duplicate / reorder / delete camera presets
- Pie menu on a single hotkey, shows the live preset list
- Full state fidelity: `matrix_basis` + rotation mode, sensor size, ortho scale, lens shift, DOF focus object
- Partial apply: transform only, optics only, DOF only
- Keyframe mode: apply a preset into a camera animation instead of hard-setting values
- Smooth transition (transform) with configurable duration
- JSON export / load for sharing preset libraries
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

Headless behaviour tests (71 checks):

```bat
blender --background --factory-startup --python tests\run_tests.py
```

Install verification against an isolated profile (does not touch your settings):

```bat
set "BLENDER_USER_RESOURCES=%TEMP%\cpm_profile"
mkdir "%TEMP%\cpm_profile\extensions"
blender --background --factory-startup --python tests\install_check.py
```

## Layout

```
camera_preset_manager/   extension package (manifest + modules)
tests/                   static check, headless suite, build helpers
SPEC.md                  full technical specification (v1.1)
```

`SPEC.md` is the source of truth for behaviour, constraints and the Definition of Done.
