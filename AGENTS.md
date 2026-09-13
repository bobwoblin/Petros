# Repository rules

## Before editing

- Read the affected SQF/Python code and direct callers before changing behavior.
- Trace PREP/XEH, `CfgFunctions`, Pythia, Discord, BattlEye RCon, and Antistasi boundaries touched by the change.
- Keep changes focused on the request.
- Reuse the standard library, Arma, CBA, Pythia, and existing project code before adding helpers or dependencies.
- Fix shared problems where they actually originate.

## Code style

- Follow ACE3/CBA conventions on the SQF side.
- The component is `addons/main`; `$PBOPREFIX$` is `x\petros\addons\main`.
- Use four spaces, LF, UTF-8, no tabs, and no trailing whitespace.
- Keep `config.cpp` as an include index and put substantial config in focused headers.
- Keep one SQF function per `functions/fnc_*.sqf` file.
- Include `../script_component.hpp` first in normal SQF functions.
- Use ACE-style function headers: `Author`, `Arguments`, `Return Value`, `Example`, `Public`.
- Register normal mission functions with PREP/XEH.
- `fnc_preStart.sqf` stays under engine `CfgFunctions` `preStart`; it must run before CBA preInit.
- Use `FUNC`/`QFUNC`, `GVAR`/`QGVAR`, and path macros inside first-party SQF.
- Use CBA scheduling for recurring mission work.
- Keep the Python runtime standard-library-only.
- Keep functions focused; don't add generic command or transport abstraction without a current use.

## Petros rules

- First-party SQF names use `petros_fnc_*` and `petros_*`.
- Keep Discord, RCon, extension, and mission payload validation at their input boundaries.
- Keep admin authorization and command-channel restrictions in place.
- Don't add arbitrary RCon, SQF, shell, kick/ban, or generic remote-execution commands.
- Keep `python_code/config.local.py` local and untracked. Never commit tokens or RCon credentials.
- Keep `config.local.py` server-only. Player Rich Presence uses its independent `RICH_PRESENCE_*` settings; publish only their explicit public allowlist to clients, never bot or RCon credentials.
- Keep player Rich Presence inside Petros through Pythia and the local Discord IPC protocol; do not add another Rich Presence addon or client DLL without a concrete requirement.
- Keep direct Antistasi save-selector/global access isolated. Re-check call sites marked with `ponytail:` when upstream behavior changes.
- The scheduled `A3A_fnc_saveLoop` call stays scheduled because the upstream function requires it.
- When renaming a command, key, or first-party symbol, update every caller, test, and document in the same change.

## Repository hygiene

- Don't commit credentials, local machine state, HEMTT output, Python caches, or private BI keys.
- Don't add contributor/process files that a one-owner repository doesn't use.
- Add or update a focused test when changing protocol, authorization, parsing, RCon, or command behavior.

## Checks

```text
python tools/validate_source.py
python python_code/selftest.py
hemtt check --pedantic
hemtt build
```

Use `tests/runtime/smoke.sqf` and the manual checks in `tests/runtime/README.md` for mission-side behavior.
