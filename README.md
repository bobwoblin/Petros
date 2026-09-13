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

`config.local.py` may contain secrets, is ignored by Git, and must not be committed. It is only used by the server-side Discord bridge.

Discord embed styling is intentionally separate from credentials. Edit `python_code/presentation.py` to change shared author/footer text, event titles/descriptions, and colors without touching bot logic.

Petros connects to Discord with Gateway intents `0` and to BattlEye RCon on `127.0.0.1`. If RCon is down, mission load/restart/selection commands are unavailable. Antistasi information and save commands can still work once the mission bridge is running.

### Discord Rich Presence

Configure the **server's** `python_code/config.local.py` (copy the existing `config.example.py`). No Python/SQF/HPP source edits or operator-specific builds are needed.

1. Create/use your Discord Developer Portal application and copy its Application ID below. This player application can differ from the bot's `APPLICATION_ID`.
2. Optionally upload Rich Presence art to that application and enter its asset keys. Empty keys omit the images and their text.
3. Start/restart the Petros server. Joining players automatically receive the public settings; they join with CBA, Pythia, and Petros installed and Discord desktop activity sharing enabled.

```python
RICH_PRESENCE_ENABLED = True
RICH_PRESENCE_APPLICATION_ID = "YOUR_DISCORD_APPLICATION_ID"
RICH_PRESENCE_UPDATE_INTERVAL = 15  # Seconds; minimum 15, maximum 300.
RICH_PRESENCE_DETAILS = "Antistasi Ultimate"
RICH_PRESENCE_LARGE_IMAGE_KEY = ""
RICH_PRESENCE_LARGE_IMAGE_TEXT = ""
RICH_PRESENCE_SMALL_IMAGE_KEY = ""
RICH_PRESENCE_SMALL_IMAGE_TEXT = ""

BOT_PRESENCE_STATUS = "online"  # online, idle, dnd, invisible
BOT_PRESENCE_ACTIVITY_TYPE = "playing"  # playing, listening, watching, competing
BOT_PRESENCE_TEXT = ""  # Empty uses the existing SERVER_NAME.
```

Discord supplies the player application's display name from the Developer Portal; there is no separate Petros application-name override. `RICH_PRESENCE_DETAILS` is static descriptive text; current server name, map, human player count/mission capacity, group side, and available war level still come from live Arma/Antistasi state. Bot activity retains live map/count/war information after its configured text.

The existing server config loader validates these values once on startup. Invalid intervals use 15 seconds; out-of-range intervals are clamped to 15–300, with one warning when enabled. Invalid bot activity types warn once and use `playing`; legacy numeric types 0/2/3/5 remain accepted. Missing/malformed player IDs log one useful server message and disable player presence for that session. Explicitly disabled presence is silent; omitted settings default to disabled. Correct the config and restart the server to apply changes. Existing bot credentials remain required for normal Petros startup.

Server postInit exports only an explicit public allowlist through Pythia and broadcasts `petros_richPresenceConfig` to current and joining players. Clients never load or receive `config.local.py`, bot credentials, or RCon credentials. There is no compile-time Arma limitation: the old `CfgRichPresence.hpp` was removed because these are runtime values. Operators configure each value in one place.

Client postInit waits for public settings, the player, gameplay display, and Pythia. The CBA handler samples state at the configured interval. One Python worker owns local Windows Discord IPC; Pythia calls only queue the latest activity. Changed activity is sent at most once per 15 seconds, retaining the session timer. Unchanged activity uses IPC PING instead of another SET_ACTIVITY. Pipe reads/writes have two-second deadlines. Connection failures close the pipe and retry after 15 seconds, replaying the latest activity after READY. Failures are logged once per outage, followed by a recovery message.

Gameplay display unload removes the handler and queues a clear, closes IPC, and resets the session timer. Arma process exit also releases the pipe. `update_presence` returning true means queued, not confirmed by Discord; client Python logs report actual RPC failures.

Petros's bot uses its existing Gateway connection and restores configured activity/status after READY or RESUMED. The existing 12-second campaign monitor supplies dynamic values. Changed activity is sent at most once per 15 seconds; unchanged activity is suppressed. New mission postInit resets campaign values; when mission command polling stops for five seconds the activity falls back to its configured text/server name. Send failures log and use the existing reconnect path.

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
