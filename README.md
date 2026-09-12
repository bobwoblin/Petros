# Petros

Petros is a Discord operations bridge and client Rich Presence addon for Antistasi Ultimate. SQF exchanges command and event payloads with a Pythia-hosted Python module. Discord, Discord Rich Presence, and BattlEye RCon I/O stay in Python, which uses only the standard library.

## Layout

Petros has one HEMTT component at `addons/main`:

```text
x\petros\addons\main -> petros_main.pbo
```

First-party SQF functions and state use `petros_fnc_*` and `petros_*`. Pythia calls use the Python module name, for example `Petros.start` and `Petros.update_presence`.

`CfgFunctions` starts `fnc_preStart.sqf` before a mission loads so the server-side Python bridge can come up early. Mission-side functions are registered through PREP/XEH. Recurring mission work uses CBA scheduling. The Antistasi `A3A_fnc_saveLoop` call runs in scheduled execution because the upstream function requires it.

## Commands

Public commands:

```text
/help /ping /status /players /campaign /territory
/locations /war /resources /missions
```

Admin server commands:

```text
/servermissions /loadmission /restartmission /missionselect
```

Admin Antistasi commands:

```text
/saves /loadsave /save /announce
```

There are no arbitrary RCon, SQF, shell, kick/ban, or generic remote-execution commands.

## Configuration

Copy `python_code/config.example.py` to `python_code/config.local.py` and set the server values:

```python
BOT_TOKEN = "..."
APPLICATION_ID = "..."
GUILD_ID = "..."

COMMAND_CHANNEL_ID = ""
EVENT_CHANNEL_ID = ""
SERVER_NAME = "Antistasi Server"

RCON_PORT = 2301
RCON_PASSWORD = "..."

ADMIN_USER_IDS = ["..."]
ADMIN_ROLE_IDS = []
```

`config.local.py` is ignored and should stay local. It is only used by the server-side Discord bridge.

Discord embed styling is intentionally separate from credentials. Edit `python_code/presentation.py` to change shared author/footer text, event titles/descriptions, and colors without touching bot logic.

Petros connects to Discord with Gateway intents `0` and to BattlEye RCon on `127.0.0.1`. If RCon is down, mission load/restart/selection commands are unavailable. Antistasi information and save commands can still work once the mission bridge is running.

### Player Discord Rich Presence

Rich Presence is built into Petros. Players do not need a separate Discord Rich Presence Arma mod.

Edit `addons/main/CfgRichPresence.hpp` before building:

```cpp
class CfgPetrosRichPresence {
    applicationID = "YOUR_DISCORD_APPLICATION_ID";
    enabled = 1;
    updateInterval = 15;
    details = "Antistasi Ultimate";
    largeImageKey = "";
    largeImageText = "Bobby's Junta";
};
```

Create or use a Discord application named **Bobby's Junta** and put its public Application ID in `applicationID`. Discord uses that application name for the `Playing Bobby's Junta` line.

When a player joins with Petros and Pythia loaded as normal client mods, Petros connects to that player's local Discord desktop IPC and publishes:

- `Playing Bobby's Junta`
- `Antistasi Ultimate`
- map name and current/max player count
- elapsed session time
- optional large image asset configured in the Discord application

The presence refreshes every 15 seconds by default and clears when the Arma gameplay display unloads, including mission exit or disconnect. Failure to reach Discord is non-fatal and does not affect gameplay.

## Antistasi integration

`/saves` reads the save catalog for the current map. `/loadsave` selects a save through Antistasi's normal start-game path and refuses campaign switching after the campaign has started.

Direct access to Antistasi mission globals/save-selection functions is kept in a small number of marked call sites because those names can change upstream.

## Dependencies and deployment

Petros requires CBA common and Pythia. The server-side operations bridge can use:

```text
"-serverMod=@Pythia;@Petros"
```

Players who should publish Rich Presence must load CBA, Pythia, and Petros on the client. No additional Rich Presence addon or Petros-specific DLL is required.

HEMTT packages the addon and the required files from `python_code/`. `config.local.py` is excluded from releases.

## Build

Use HEMTT `v1.21.0` and Python 3.13+.

```text
python tools/validate_source.py
python python_code/selftest.py
hemtt check --pedantic
hemtt build
```

The Python self-test covers command validation/authorization, Discord transport, Discord Rich Presence IPC framing, BattlEye RCon framing and fragmentation, mission discovery, command registration, limits, typed options, and the standard-library-only runtime requirement.

See `tests/runtime/README.md` for runtime checks.

## Release

Set the version in `.hemtt/project.toml`. Pushes to `main` run validation plus the HEMTT check/build. A matching semantic tag such as `v0.1.0` runs the signed release workflow and publishes only `Petros-<version>.zip` to GitHub Releases. The ZIP opens to `@Petros/`, with the PBOs, signatures, public key, and release files inside.

## License

Petros is licensed under the GNU General Public License v2.0. See LICENSE for details.

Arma 3, Antistasi Ultimate, Pythia, Discord, and other referenced projects remain the property of their respective authors and are subject to their own licenses.

SPDX-License-Identifier: GPL-2.0-only
