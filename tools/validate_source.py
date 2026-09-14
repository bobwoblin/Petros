#!/usr/bin/env python3
"""Validate repository-wide ACE/CBA source and public-repo invariants."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
SKIP_PARTS = {".git", ".hemttout", ".venv", "__pycache__"}
TEXT_SUFFIXES = {".sqf", ".cpp", ".hpp", ".md", ".py", ".toml", ".yml", ".yaml", ".json", ".xml", ".txt"}
OWN_FUNCTION_NAMESPACES = ['petros']

REQUIRED_REPO_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".hemtt/project.toml",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "mod.cpp",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        ERRORS.append(f"can't read {path.relative_to(ROOT)}: {exc}")
        return ""


def tracked_files() -> list[Path]:
    return [
        path for path in ROOT.rglob("*")
        if path.is_file() and not any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts)
    ]


for relative in sorted(REQUIRED_REPO_FILES):
    check((ROOT / relative).is_file(), f"missing repository file: {relative}")

files = tracked_files()

# Public repositories mustn't contain local credentials or private signing keys.
for path in files:
    relative = path.relative_to(ROOT)
    lower = path.name.lower()
    check(lower != "config.local.py", f"private local config is tracked: {relative}")
    check(not lower.endswith((".biprivatekey", ".hemttprivatekey")), f"private signing key is tracked: {relative}")

# Keep source deterministic across platforms and editors.
for path in files:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "$PBOPREFIX$":
        continue
    data = path.read_bytes()
    check(b"\r\n" not in data and b"\r" not in data, f"non-LF line endings: {path.relative_to(ROOT)}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        continue
    check("\t" not in text, f"tab character in text source: {path.relative_to(ROOT)}")
    check(all(line == line.rstrip() for line in text.splitlines()), f"trailing whitespace: {path.relative_to(ROOT)}")
    check(not text or text.endswith("\n"), f"missing final newline: {path.relative_to(ROOT)}")

# Parse deterministic metadata and documentation formats with the standard library.
for path in (p for p in files if p.suffix.lower() == ".toml"):
    try:
        tomllib.loads(read(path))
    except tomllib.TOMLDecodeError as exc:
        ERRORS.append(f"invalid TOML {path.relative_to(ROOT)}: {exc}")
for path in (p for p in files if p.suffix.lower() == ".py"):
    try:
        compile(read(path), str(path), "exec")
    except SyntaxError as exc:
        ERRORS.append(f"invalid Python {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")

addons_root = ROOT / "addons"
addons = sorted(path for path in addons_root.iterdir() if path.is_dir()) if addons_root.is_dir() else []
check(bool(addons), "repository has no addons")

project = tomllib.loads(read(ROOT / ".hemtt/project.toml"))
project_prefix = project.get("prefix", "")
mainprefix = project.get("mainprefix", "")
check(bool(project_prefix), "HEMTT project prefix is missing")
check(mainprefix == "x", "HEMTT mainprefix must be x")

# Every component uses the repository ACE/CBA-style scaffold and shared mod header.
script_mods = sorted(addons_root.glob("*/script_mod.hpp"))
check(len(script_mods) == 1, f"expected exactly one shared script_mod.hpp, found {len(script_mods)}")
shared_component = script_mods[0].parent.name if len(script_mods) == 1 else ""
if script_mods:
    shared_mod = read(script_mods[0])
    check(f"#define MAINPREFIX {mainprefix}" in shared_mod, "script_mod.hpp MAINPREFIX differs from HEMTT mainprefix")
    check(f"#define PREFIX {project_prefix}" in shared_mod, "script_mod.hpp PREFIX differs from HEMTT prefix")
    check(re.search(r'^#define REQUIRED_VERSION\s+\d+(?:\.\d+)?$', shared_mod, re.M) is not None,
          "script_mod.hpp must define REQUIRED_VERSION once")
    check('#define MOD_AUTHOR "Bobby"' in shared_mod, "script_mod.hpp MOD_AUTHOR is invalid")
    check((script_mods[0].parent / "script_macros.hpp").is_file(), "missing shared script_macros.hpp")

check((ROOT / "tests/runtime/smoke.sqf").is_file(), "missing tests/runtime/smoke.sqf")

# Physical component names, virtual PBO paths, and HEMTT output names share one canonical namespace.
for addon in addons:
    prefix = addon / "$PBOPREFIX$"
    expected_prefix = f"{mainprefix}\\{project_prefix}\\addons\\{addon.name}"
    check(prefix.is_file() and read(prefix).strip() == expected_prefix,
          f"non-canonical $PBOPREFIX$ for {addon.relative_to(ROOT)}: expected {expected_prefix}")
    check((addon / "CfgPatches.hpp").is_file(), f"missing CfgPatches.hpp: {addon.relative_to(ROOT)}")


    component = addon / "script_component.hpp"
    check(component.is_file(), f"missing script_component.hpp: {addon.relative_to(ROOT)}")
    component_text = read(component)
    check(f"#define COMPONENT {addon.name}" in component_text,
          f"script_component.hpp COMPONENT doesn't match addon directory: {component.relative_to(ROOT)}")
    check(re.search(r'^#define COMPONENT_NAME\s+"[^"]+"$', component_text, re.M) is not None,
          f"script_component.hpp must define COMPONENT_NAME: {component.relative_to(ROOT)}")
    expected_mod_include = rf'#include "\{mainprefix}\{project_prefix}\addons\{shared_component}\script_mod.hpp"'
    check(expected_mod_include in component_text,
          f"script_component.hpp must include the shared mod header: {component.relative_to(ROOT)}")
    expected_macro_include = rf'#include "\{mainprefix}\{project_prefix}\addons\{shared_component}\script_macros.hpp"'
    check(expected_macro_include in component_text,
          f"component must include the shared project macros: {component.relative_to(ROOT)}")
    check(
        "#define FUNC(var1) FUNCMAIN(var1)" in component_text
        and "#define GVAR(var1) GVARMAIN(var1)" in component_text,
        f"component runtime namespace macros are invalid: {component.relative_to(ROOT)}",
    )

    patch_text = read(addon / "CfgPatches.hpp")
    check(re.search(r'class\s+CfgPatches\s*\{\s*class\s+ADDON\s*\{', patch_text, re.S) is not None,
          f"CfgPatches must use class ADDON: {(addon / 'CfgPatches.hpp').relative_to(ROOT)}")
    check("name = COMPONENT_NAME;" in patch_text,
          f"CfgPatches name must use COMPONENT_NAME: {(addon / 'CfgPatches.hpp').relative_to(ROOT)}")
    check("author = MOD_AUTHOR;" in patch_text,
          f"CfgPatches author must use MOD_AUTHOR: {(addon / 'CfgPatches.hpp').relative_to(ROOT)}")
    check("requiredVersion = REQUIRED_VERSION;" in patch_text,
          f"CfgPatches requiredVersion must use REQUIRED_VERSION: {(addon / 'CfgPatches.hpp').relative_to(ROOT)}")
    check(re.search(r'requiredVersion\s*=\s*\d', patch_text) is None,
          f"CfgPatches contains a literal requiredVersion: {(addon / 'CfgPatches.hpp').relative_to(ROOT)}")

    config = addon / "config.cpp"
    check(config.is_file(), f"missing config.cpp: {addon.relative_to(ROOT)}")
    cfg = read(config)
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", "", cfg, flags=re.S)
    check(re.search(r"\bclass\s+[A-Za-z_]", without_comments) is None,
          f"config.cpp contains declarations instead of include-only composition: {config.relative_to(ROOT)}")
    for include in re.findall(r'^\s*#include\s+"([^"]+)"', cfg, re.M):
        check(
            not include.startswith("\\"),
            f"config.cpp shouldn't directly include external absolute paths: {config.relative_to(ROOT)}",
        )
        target = addon / Path(include.replace("\\", "/"))
        check(target.is_file(), f"missing include {include} from {config.relative_to(ROOT)}")


# Executable config expressions use QUOTE rather than hand-escaped string literals.
for path in (p for p in files if p.suffix.lower() in {".hpp", ".cpp"} and "generated" not in p.parts):
    source = read(path)
    for match in re.finditer(r"\b(?:condition|statement|onLoad|init)\s*=\s*\"([^\"]*)\";", source):
        check(match.group(1) == "", f"config code must use QUOTE(...): {path.relative_to(ROOT)}")

# ACE-style SQF functions and CBA XEH/PREP lifecycle.
all_function_files = sorted(addons_root.rglob("functions/*.sqf"))
function_files = [path for path in all_function_files if path.name.startswith("fnc_")]
invalid_function_names = [path for path in all_function_files if not path.name.startswith("fnc_")]
check(
    not invalid_function_names,
    "function files must use fnc_*.sqf: "
    + ", ".join(str(p.relative_to(ROOT)) for p in invalid_function_names),
)
required_header = ("Author:", "Arguments:", "Return Value:", "Example:", "Public:")

for path in function_files:
    text = read(path)
    lines = text.splitlines()
    check(bool(lines) and lines[0] == '#include "../script_component.hpp"',
          f"function must include ../script_component.hpp first: {path.relative_to(ROOT)}")
    head = "\n".join(lines[:50])
    for marker in required_header:
        check(marker in head, f"missing {marker} function header field: {path.relative_to(ROOT)}")
    check("Author: Bobby" in head, f"function author header is invalid: {path.relative_to(ROOT)}")
    public = re.search(r"Public:\s*(Yes|No)\b", head)
    check(public is not None, f"Public header must be Yes or No: {path.relative_to(ROOT)}")

    close = text.find("*/")
    body = text[close + 2:] if close >= 0 else text
    body_lines = [line for line in body.splitlines() if line.strip()]
    check(
        len(body_lines) <= 250,
        f"function body exceeds ACE 250-line limit ({len(body_lines)}): {path.relative_to(ROOT)}",
    )

    args_match = re.search(r"Arguments:\s*(?P<args>.*?)\n\s*\*\s*Return Value:", head, re.S)
    if public and public.group(1) == "Yes" and args_match and "None" not in args_match.group("args"):
        check(re.search(r"\bparams\s*\[\s*\[", body) is not None,
              f"public function arguments must use typed params: {path.relative_to(ROOT)}")

for addon in addons:
    functions_dir = addon / "functions"
    if not functions_dir.is_dir():
        continue

    component = addon / "script_component.hpp"
    prep_path = addon / "XEH_PREP.hpp"
    preinit_path = addon / "XEH_preInit.sqf"
    events_path = addon / "CfgEventHandlers.hpp"
    check(component.is_file(), f"addon with functions lacks script_component.hpp: {addon.relative_to(ROOT)}")
    check(prep_path.is_file(), f"addon with functions lacks XEH_PREP.hpp: {addon.relative_to(ROOT)}")
    check(preinit_path.is_file(), f"addon with functions lacks XEH_preInit.sqf: {addon.relative_to(ROOT)}")
    check(events_path.is_file(), f"addon with functions lacks CfgEventHandlers.hpp: {addon.relative_to(ROOT)}")

    component_text = read(component)
    check("#define FUNC" in component_text and "#define GVAR" in component_text,
          f"component runtime namespace macros are missing: {component.relative_to(ROOT)}")

    event_text = read(events_path)
    check("Extended_PreInit_EventHandlers" in event_text,
          f"function addon lacks CBA preInit XEH registration: {events_path.relative_to(ROOT)}")
    if (addon / "XEH_postInit.sqf").is_file():
        check("Extended_PostInit_EventHandlers" in event_text,
              f"postInit file isn't registered through CBA XEH: {events_path.relative_to(ROOT)}")

    preinit_text = read(preinit_path)
    check('#include "XEH_PREP.hpp"' in preinit_text,
          f"XEH_preInit doesn't compile XEH_PREP.hpp: {preinit_path.relative_to(ROOT)}")

    cfgfunctions = addon / "CfgFunctions.hpp"
    explicit_prestart: set[str] = set()
    if cfgfunctions.is_file():
        cfgfunctions_text = read(cfgfunctions)
        explicit_refs = set(re.findall(r"fnc_([A-Za-z0-9_]+)\.sqf", cfgfunctions_text))
        check(
            explicit_refs == {"preStart"},
            f"CfgFunctions is reserved for the lifecycle-required preStart exception: {cfgfunctions.relative_to(ROOT)}",
        )
        check("preStart = 1;" in cfgfunctions_text,
              f"CfgFunctions preStart exception is missing preStart = 1: {cfgfunctions.relative_to(ROOT)}")
        explicit_prestart = {"preStart"}

    prep_text = read(prep_path)
    prepped = set(re.findall(r"\bPREP\s*\(\s*([A-Za-z0-9_]+)\s*\)", prep_text))
    names = {path.stem.removeprefix("fnc_") for path in functions_dir.glob("fnc_*.sqf")}
    check(
        names - explicit_prestart == prepped,
        f"XEH_PREP doesn't exactly match addon functions in {addon.relative_to(ROOT)}: "
        f"expected {sorted(names - explicit_prestart)}, got {sorted(prepped)}",
    )

# Internal function bodies use component macros instead of spelling their own public function namespace.
for path in function_files:
    text = read(path)
    close = text.find("*/")
    body = text[close + 2:] if close >= 0 else text
    for namespace in OWN_FUNCTION_NAMESPACES:
        check(f"{namespace}_fnc_" not in body,
              f"internal call bypasses FUNC/QFUNC macros in {path.relative_to(ROOT)}: {namespace}_fnc_*")
    check(re.search(r'"(?:GVAR|QGVAR|FUNC|QFUNC)\(', body) is None,
          f"quoted macro invocation would become a literal key/name: {path.relative_to(ROOT)}")


# Petros lifecycle, scheduler, bridge, and secret-handling contracts.
ADDON = ROOT / "addons/main"
check(read(ADDON / "$PBOPREFIX$").strip() == r"x\petros\addons\main", "Petros PBO prefix changed")
cfgfunctions = read(ADDON / "CfgFunctions.hpp")
check(r'file = QPATHTOF(functions\fnc_preStart.sqf);' in cfgfunctions and "preStart = 1;" in cfgfunctions,
      "Petros preStart lifecycle exception changed")
post_init = read(ADDON / "functions/fnc_postInit.sqf")
check("CBA_fnc_addPerFrameHandler" in post_init, "Petros command polling isn't CBA-scheduled")
check("CBA_fnc_waitUntilAndExecute" in post_init, "Petros campaign startup isn't CBA-scheduled")
check(
    "[] spawn" not in post_init and "while {true}" not in post_init,
    "Petros postInit reintroduced unmanaged scheduler loops",
)
handle = read(ADDON / "functions/fnc_handleCommand.sqf")
check("[] spawn A3A_fnc_saveLoop" in handle, "Antistasi saveLoop scheduled-context compatibility call changed")
check("ponytail:" in handle, "private Antistasi scheduled-context dependency isn't marked as intentional debt")
garrisons = read(ADDON / "functions/fnc_getGarrisons.sqf")
check("A3A_fnc_getGarrison" in garrisons and "A3A_fnc_countGarrison" in garrisons,
      "garrison adapter must use Antistasi's centralized read helpers")
garage = read(ADDON / "functions/fnc_getGarage.sqf")
check("HR_GRG_fnc_getSaveData" in garage,
      "garage adapter must use Antistasi's public server save-data API")
towns = read(ADDON / "functions/fnc_getTowns.sqf")
check("A3A_townData" in towns and "ponytail:" in towns,
      "town adapter's upstream record dependency must remain isolated and marked")
monitor = read(ADDON / "functions/fnc_startMonitoring.sqf")
check('"markerChange"' in monitor and "A3A_Events_fnc_addEventListener" in monitor,
      "territory monitoring must subscribe to Antistasi's marker event")
poll = read(ADDON / "functions/fnc_pollCommands.sqf")
check("Petros.observe_save" in poll,
      "command polling must forward authoritative save-state edges")
python_bridge = read(ROOT / "python_code/__init__.py")
check('_rcon_command("#restart")' in python_bridge and '"kind": "safe_restart"' in python_bridge,
      "safe restart must retain its fixed RCon command path")
check((ROOT / "python_code/config.example.py").is_file(), "missing public Python configuration example")
check((ROOT / "python_code/selftest.py").is_file(), "missing Python bridge self-test")
check((ROOT / "tests/runtime/README.md").is_file(), "missing runtime verification matrix")


if ERRORS:
    for error in ERRORS:
        print(f"ERROR: {error}")
    sys.exit(1)

print(f"OK: repository invariants valid ({len(function_files)} SQF functions across {len(addons)} addons)")
