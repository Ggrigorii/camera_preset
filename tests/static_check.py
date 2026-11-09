"""Static checks that run on plain Python (no Blender required).

Usage:
    python tests/static_check.py

Covers: byte-compilation, preset field/model consistency, unique operator ids,
operator ids referenced by the UI, and manifest sanity.
"""

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "camera_preset_manager")

FAILURES = []


def check(condition, message):
    if condition:
        print("  ok    : " + message)
    else:
        FAILURES.append(message)
        print("  FAILED: " + message)


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def python_files():
    return sorted(
        os.path.join(PACKAGE, name)
        for name in os.listdir(PACKAGE)
        if name.endswith(".py")
    )


def test_compiles():
    print("[compile]")
    for path in python_files():
        try:
            compile(read(path), path, "exec")
        except SyntaxError as error:
            check(False, "{}: {}".format(os.path.basename(path), error))
        else:
            check(True, "{} compiles".format(os.path.basename(path)))


def _preset_class_fields():
    tree = ast.parse(read(os.path.join(PACKAGE, "properties.py")))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "CAMPRESET_PG_preset":
            return [target.id for child in node.body
                    if isinstance(child, ast.AnnAssign)
                    for target in [child.target] if isinstance(target, ast.Name)]
    return []


def _preset_field_constant():
    tree = ast.parse(read(os.path.join(PACKAGE, "properties.py")))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PRESET_FIELDS"
            for target in node.targets
        ):
            return [element.value for element in node.value.elts]
    return []


def test_model_consistency():
    print("[model]")
    fields = _preset_class_fields()
    declared = _preset_field_constant()

    check(bool(declared), "PRESET_FIELDS is defined")
    check(declared[:1] == ["name"], "PRESET_FIELDS starts with 'name'")
    check(len(set(declared)) == len(declared), "PRESET_FIELDS has no duplicates")
    missing = [field for field in declared if field not in fields]
    extra = [field for field in fields if field not in declared]
    check(not missing, "every PRESET_FIELDS entry exists on the group: {}".format(missing or "ok"))
    check(not extra, "every group field is exported: {}".format(extra or "ok"))


def test_operator_ids():
    print("[operators]")
    defined = {}
    for path in python_files():
        text = read(path)
        for match in re.finditer(r'bl_idname\s*=\s*"([a-z_][a-z0-9_.]*)"', text):
            identifier = match.group(1)
            if identifier in defined:
                check(False, "duplicate bl_idname {} in {} and {}".format(
                    identifier,
                    os.path.basename(defined[identifier]),
                    os.path.basename(path),
                ))
            else:
                defined[identifier] = path
    check(True, "{} registered identifiers".format(len(defined)))

    for identifier in sorted(defined):
        check(
            identifier.count(".") <= 1,
            "identifier '{}' follows the module.operator convention".format(identifier),
        )

    used = set()
    for path in python_files():
        for match in re.finditer(r'"([a-z_]+\.[a-z_]+)"', read(path)):
            used.add(match.group(1))
    # Only report cam_preset.* ids that are referenced outside their definition.
    referenced = {
        identifier for identifier in used
        if identifier.startswith("cam_preset.")
    }
    unknown = sorted(referenced - set(defined))
    check(not unknown, "all referenced cam_preset.* ids exist: {}".format(unknown or "ok"))


REQUIRED_MANIFEST = (
    "schema_version",
    "id",
    "version",
    "name",
    "tagline",
    "maintainer",
    "type",
    "blender_version_min",
    "license",
)


def test_manifest():
    print("[manifest]")
    text = read(os.path.join(PACKAGE, "blender_manifest.toml"))
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        values[key.strip()] = raw.strip()

    for key in REQUIRED_MANIFEST:
        check(key in values, "manifest has '{}'".format(key))

    identifier = values.get("id", "").strip('"')
    check(
        re.match(r"^[a-z][a-z0-9_]*$", identifier) is not None,
        "manifest id '{}' is lowercase with underscores".format(identifier),
    )
    version = values.get("version", "").strip('"')
    check(
        re.match(r"^\d+\.\d+\.\d+$", version) is not None,
        "manifest version '{}' is semver".format(version),
    )
    tagline = values.get("tagline", "").strip('"')
    check(len(tagline) <= 64, "tagline is {} characters (<= 64)".format(len(tagline)))
    check(
        values.get("type", "").strip('"') == "add-on",
        "manifest type is 'add-on'",
    )
    check(
        'SPDX:' in values.get("license", ""),
        "license uses the SPDX: prefix",
    )


def test_no_bl_info():
    print("[extension format]")
    text = read(os.path.join(PACKAGE, "__init__.py"))
    check("bl_info" not in text, "__init__.py does not define bl_info")
    check("def register(" in text, "__init__.py defines register()")
    check("def unregister(" in text, "__init__.py defines unregister()")


def main():
    test_compiles()
    test_model_consistency()
    test_operator_ids()
    test_manifest()
    test_no_bl_info()

    print()
    if FAILURES:
        print("FAILED: {} check(s)".format(len(FAILURES)))
        for message in FAILURES:
            print("  - " + message)
        return 1
    print("All static checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
