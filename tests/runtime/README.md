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

Rich Presence client check:

1. Configure `CfgPetrosRichPresence.applicationID` with a Discord application named `Bobby's Junta`, then rebuild Petros.
2. Start the Discord desktop client and Arma with CBA, Pythia, and Petros loaded as normal client mods.
3. Join the Antistasi server. Confirm the player's Discord profile shows `Playing Bobby's Junta`, `Antistasi Ultimate`, the current map/player count, and an elapsed timer.
4. Join or leave with another player and confirm the count updates within the configured interval.
5. Abort to the lobby or disconnect and confirm the Petros Rich Presence clears.
6. Repeat with Discord closed. Confirm gameplay is unaffected and Petros only reports the unavailable local Discord client instead of failing the mission.
