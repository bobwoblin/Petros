# Runtime verification

Run `smoke.sqf` first. The RPT must end with `[petros][TEST] COMPLETE failures=0`.

The Python self-test covers bridge/protocol logic without Arma. Before release, test the mission-facing path on a dedicated server:

1. Start with CBA, Pythia, Petros, and Antistasi Ultimate. Confirm the Python bridge starts during `preStart` before a mission is loaded.
2. Join the campaign and confirm `postInit` starts command polling and campaign monitoring once.
3. Run the public Discord commands and check that they return current campaign/player data without admin actions.
4. Run each configured admin command with an authorized account, then confirm the same command is denied for an unauthorized account.
5. Check save listing/loading and confirm campaign switching is refused after campaign start.
6. Stop BattlEye RCon and confirm mission discovery/load/restart commands fail safely; restore RCon and confirm they recover.
7. Restart the mission and server. Confirm CBA handlers stay single-instance and stale command/event payloads don't replay.
8. Review RPT and bridge logs for secrets. Make sure tokens and RCon credentials never appear in logs.

Rich Presence client check (requires Arma and Discord desktop on Windows):

1. Install updated Petros. Copy `python_code/config.example.py` to the server's `config.local.py` and set bot credentials plus `RICH_PRESENCE_ENABLED = True` and your own `RICH_PRESENCE_APPLICATION_ID`. Use a different application from the bot to verify independence. Optionally set both large/small image keys and text to assets in that player application. Enable Discord activity sharing; start the server without source edits or rebuilding for your settings.
2. Start Discord and Arma with CBA, Pythia, and Petros as normal client mods. Players must not need `config.local.py`. Run `smoke.sqf` in the mission and require zero failures.
3. Join the Antistasi server. Check `Playing <your application name>`, current server/Antistasi details, map, human count/mission capacity, group side, available war level, and elapsed timer. Confirm no client config/token error appears in Pythia/RPT logs.
4. Join/leave with another human; change group side or advance war level through normal gameplay. Allow up to 30 seconds with default sampling/sending intervals plus Discord UI propagation. Verify changed values and an uninterrupted timer. Headless clients must not increase the human count.
5. Keep state unchanged for one minute. For wire-level verification, attach a debugger to Pythia's Python runtime and count calls to `_presence_send_locked`: no repeated SET_ACTIVITY should occur. `_presence_sync` should use opcode 3 PING instead; that local heartbeat does not update activity.
6. Exit Discord completely while remaining in-game. Confirm no Arma hang and one `Rich Presence unavailable` message per outage. Restart Discord without changing game state; allow up to 35 seconds for detection/reconnect plus UI propagation. Presence and its original timer should return. Repeat by joining with Discord initially closed, then opening it.
7. Abort/disconnect: verify presence clears, the CBA handler is removed, and IPC closes. Rejoin and verify a fresh timer and one handler. Exit Arma normally and check cleanup; also check process termination releases presence through Discord's pipe-disconnect handling.
8. In server `config.local.py`, try an empty and then a malformed player Application ID with presence enabled; restart the server for each. Require one useful server config warning, `petros_richPresenceConfig` equal to `[]`, no client presence handler, and no IPC initialization. Then explicitly disable presence and require the same inactivity without error noise. Correct the ID and restart to recover.
9. Change only the config to a second owned Application ID and different large/small asset keys/text. Restart the server and join again; verify the second app name and both image captions. Clear both image keys and restart; activity must work without art. No client source/config changes should be needed. Join after campaign startup to check JIP delivery of the public settings, then switch to a differently configured server to check stale settings do not carry over.

Petros bot check (requires the configured dedicated server and Discord bot):

1. Start normally. Require `Started`, `Discord REST authenticated`, `Slash commands registered`, and `Gateway connected` without new errors. Set `BOT_PRESENCE_STATUS = "idle"`, `BOT_PRESENCE_ACTIVITY_TYPE = "watching"`, and a custom `BOT_PRESENCE_TEXT` in server-only `config.local.py`; after READY verify idle/Watching with that text. Also check defaults (online/Playing `SERVER_NAME`).
2. Start the campaign. Within 30 seconds, verify map/player count/available war level are appended. Compare against `/status`, `/players`, `/campaign`, and `/war`; change player count and war level and repeat. Notification settings/channel availability must not affect activity.
3. Keep state unchanged for one minute. Inspect `_ws_send_json` in a debugger: Gateway opcode 3 must not repeat; heartbeats (opcode 1) must continue.
4. Temporarily interrupt the test server's Discord connection and restore it. Require `Gateway resumed` or `Gateway connected` and restored activity even with unchanged state. Restart the bot to exercise fresh READY. Verify one Gateway connection; send failures should log and reconnect without terminating Petros.
5. Return the server to mission selection. Within 20 seconds of command polling stopping, old campaign data should disappear, leaving configured text (or `SERVER_NAME` when empty). Load/restart a mission and verify old map/war data does not carry into startup.
6. Run `/ping`, `/status`, `/players`, `/campaign`, `/war`, `/resources`, and `/missions` again. Repeat authorization, save, and RCon checks above. Presence must not affect commands or campaign monitoring.

Offline checks cover payloads, deduplication, READY/RESUMED, IPC replies/PING/errors/timeouts, worker isolation, and existing commands/transports. They cannot establish actual Discord display, application ownership/name/assets, or Arma/Pythia display-unload behavior; complete the steps above before release.
