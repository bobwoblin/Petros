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
/locations /war /resources /missions /activity
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

Client postInit waits for public settings, the player, gameplay display, and Pythia. The CBA handler samples state at the configured interval. One Python worker owns local Windows Discord IPC; Pythia calls only queue the latest activity. Changed activity is sent at most once per 15 seconds, retaining the session timer. Unchanged activity uses IPC PING instead of another SET_ACTIVITY. Native Windows pipe reads/writes have two-second deadlines, including on Pythia's Python 3.10. Connection failures close the pipe and retry after 15 seconds, replaying the latest activity after READY. Diagnostics report connection, handshake, and activity acceptance; identical errors are suppressed until recovery. Unexpected worker exits are logged and the next update starts a replacement. A [standalone local test](tests/runtime/README.md) needs only Python and Discord desktop.

Gameplay display unload removes the handler and queues a clear, closes IPC, and resets the session timer. Arma process exit also releases the pipe. `update_presence` returning true means queued, not confirmed by Discord; client Python logs report actual RPC failures.

Petros's bot uses its existing Gateway connection and restores configured activity/status after READY or RESUMED. The existing 12-second campaign monitor supplies dynamic values. Changed activity is sent at most once per 15 seconds; unchanged activity is suppressed. New mission postInit resets campaign values; when mission command polling stops for five seconds the activity falls back to its configured text/server name. Send failures log and use the existing reconnect path.

## Antistasi integration

`/saves` reads the save catalog for the current map. `/loadsave` selects a save through Antistasi's normal start-game path and refuses campaign switching after the campaign has started.

The SQF compatibility adapter capability-checks Antistasi at runtime and produces one normalized snapshot containing campaign identity, tasks, territory, HR/resources, War Level, commander, players, and integration capabilities. Missing optional state degrades that feature and produces one health transition instead of stopping the bridge.

Petros reads Antistasi Ultimate's server-owned `A3A_tasksData` records through one marked compatibility function. The upstream record is `[task ID, type, state, creation time]`; Petros derives durations and reports mission starts, success, failure, or deletion without integrating with every mission script. `/missions` shows the richer live records. Existing tasks and territory form a silent baseline on startup or campaign change, so a bridge restart does not manufacture events.

Petros subscribes to Antistasi Ultimate's supported `A3A_fnc_addEventHandler` wrapper for `A3A_event_serverInitDone`, with the existing readiness check retained for late loading and reconciliation. The centralized task updater and territory ownership changes do not publish corresponding authoritative events, so Petros retains the existing 12-second snapshot/diff monitor for those transitions rather than patching Antistasi or increasing polling frequency.

The same normalized territory transition feeds notifications, the current play-session summary, and `/activity`. Recent activity is memory-only and bounded to 75 strategic events. It excludes kill, AI, garrison, and resource-tick noise.

A play session starts when the server changes from no human players to at least one. It ends after ten player-free minutes, allowing reconnects without splitting the session. The after-action report includes duration, peak players, territory gains/losses, War Level, HR/resources deltas, mission outcomes, and changed strategic locations. Sessions, task deduplication, and recent activity intentionally reset when Petros restarts and are not persisted.

Health monitoring reports missing task/territory/resource capabilities once per degraded transition and uses three consecutive sub-10 FPS snapshots plus a 15 FPS recovery threshold. Discord Gateway and REST health remain visible in `/ping`; RCon availability is reported by the fixed commands that actually use it. Petros does not claim it can notify Discord while the Discord connection or SQF/Pythia bridge itself is unavailable.

`/loadmission` has admin-scoped autocomplete sourced from the live Antistasi `CfgMissions` catalog. Autocomplete is convenience only: the existing authorization, character validation, and fixed RCon command path remain authoritative.

Direct access to Antistasi mission globals/save-selection functions remains confined to the compatibility adapter and marked save call sites because those names can change upstream. Campaign victory/completion is deliberately unsupported in this pass because current Antistasi source does not expose one reliable server-owned completion state or event for Petros to consume.

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

The Python self-test covers command validation/authorization, Discord transport, Discord Rich Presence IPC framing, BattlEye RCon framing and fragmentation, mission discovery/autocomplete, campaign baselining, task and territory transitions, session summaries, health hysteresis, recent-activity bounds, command registration, limits, typed options, and the standard-library-only runtime requirement.

See `tests/runtime/README.md` for runtime checks.

## Release

Set the version in `.hemtt/project.toml`. Pushes to `main` run validation plus the HEMTT check/build. A matching semantic tag such as `v0.1.0` runs the signed release workflow and publishes only `Petros-<version>.zip` to GitHub Releases. The ZIP opens to `@Petros/`, with the PBOs, signatures, public key, and release files inside.

## License

Petros is licensed under the GNU General Public License v2.0. See LICENSE for details.

Arma 3, Antistasi Ultimate, Pythia, Discord, and other referenced projects remain the property of their respective authors and are subject to their own licenses.

SPDX-License-Identifier: GPL-2.0-only
