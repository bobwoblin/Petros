#include "../script_component.hpp"
/*
 * Author: Bobby
 * Executes one validated Discord interaction against current Antistasi mission state.
 *
 * Arguments:
 * 0: Discord interaction identifier <STRING>
 * 1: Command name <STRING>
 * 2: Command options <ARRAY> (default: [])
 *
 * Return Value:
 * None
 *
 * Example:
 * ["123", "status", []] call FUNC(handleCommand)
 *
 * Public: No
 */
params ["_interactionId", "_command", ["_options", []]];
if (!isServer || {isNil "py3_fnc_callExtension"}) exitWith {};

private _snapshot = call FUNC(getSnapshot);
private _ready = _snapshot get "ready";
private _title = "Petros";
private _description = "";
private _fields = [];
private _color = EMBED_COLOR_DEFAULT;
private _newline = toString [10];

switch (_command) do {
    case "status": {
        _title = "Server Status";
        _fields = [
            ["Campaign", ["Starting", "Ready"] select _ready, true],
            ["Map", _snapshot get "map", true],
            ["Players", str (_snapshot get "playerCount"), true],
            ["Server FPS", str (_snapshot get "fps"), true],
            ["Uptime", [(_snapshot get "uptime")] call FUNC(formatDuration), true],
            ["Commander", _snapshot get "commander", true]
        ];
    };
    case "players": {
        _title = "Online Players";
        private _players = _snapshot get "players";
        _description = if (_players isEqualTo []) then {
            "No human players are online."
        } else {
            _players joinString _newline
        };
        _fields = [["Count", str count _players, true]];
    };
    case "campaign": {
        _title = "Campaign";
        if (_ready) then {
            _fields = [
                ["Version", _snapshot get "version", true],
                ["Commander", _snapshot get "commander", true],
                ["War Level", str (_snapshot get "warLevel"), true],
                ["HR", str (_snapshot get "hr"), true],
                ["Resources", str (_snapshot get "resources"), true],
                ["Territory", format ["%1 / %2", _snapshot get "strategicOwned", _snapshot get "strategicTotal"], true]
            ];
        } else {
            _description = "Antistasi Ultimate is still starting.";
        };
    };
    case "territory": {
        _title = "Territory";
        if (_ready) then {
            {
                _x params ["_name", "_owned", "_total"];
                _fields pushBack [_name, format ["%1 / %2", _owned, _total], true];
            } forEach (_snapshot get "territory");
            _description = format [
                "Resistance controls %1 of %2 tracked strategic locations.",
                _snapshot get "strategicOwned",
                _snapshot get "strategicTotal"
            ];
        } else {
            _description = "Antistasi Ultimate is still starting.";
        };
    };
    case "locations": {
        _title = "Controlled Locations";
        if (_ready) then {
            private _kind = _options param [0, "all"];
            private _variable = switch (_kind) do {
                case "towns": {"citiesX"};
                case "outposts": {"outposts"};
                case "bases": {"milbases"};
                case "airports": {"airportsX"};
                case "resources": {"resourcesX"};
                case "factories": {"factories"};
                case "seaports": {"seaports"};
                default {""};
            };
            private _markers = if (_kind == "all") then {
                (missionNamespace getVariable ["markersX", []])
                - (missionNamespace getVariable ["controlsX", []])
                - ["Synd_HQ"]
            } else {
                missionNamespace getVariable [_variable, []]
            };
            if (!isNil "teamPlayer" && {!isNil "sidesX"}) then {
                _markers = _markers select { sidesX getVariable [_x, sideUnknown] isEqualTo teamPlayer };
            } else {
                _markers = [];
            };
            if (_markers isEqualTo []) then {
                _description = "No matching Resistance-controlled locations.";
            } else {
                private _shown = _markers select [0, (count _markers) min MAX_LOCATION_RESULTS];
                private _lines = _shown apply {
                    private _location = [_x] call FUNC(getLocation);
                    format ["- %1 (%2) - %3", _location # 0, _location # 1, _location # 3]
                };
                _description = _lines joinString _newline;
                if (count _markers > count _shown) then {
                    _description = format ["%1%2...and %3 more.", _description, _newline, count _markers - count _shown];
                };
                _fields = [["Count", str count _markers, true]];
            };
        } else {
            _description = "Antistasi Ultimate is still starting.";
        };
    };
    case "war": {
        _title = "War Level";
        _description = if (_ready) then {
            format ["Current War Level: **%1**", _snapshot get "warLevel"]
        } else {
            "Antistasi Ultimate is still starting."
        };
    };
    case "resources": {
        _title = "Resistance Resources";
        if (_ready) then {
            _fields = [["Resources", str (_snapshot get "resources"), true], ["HR", str (_snapshot get "hr"), true]];
        } else {
            _description = "Antistasi Ultimate is still starting.";
        };
    };
    case "missions": {
        _title = "Active Missions";
        if (_ready) then {
            private _missions = _snapshot get "missions";
            _description = if (_missions isEqualTo []) then {
                "No active Antistasi mission types are reported."
            } else {
                _missions joinString _newline
            };
            _fields = [["Count", str count _missions, true]];
        } else {
            _description = "Antistasi Ultimate is still starting.";
        };
    };
    // ponytail: Antistasi save-selector functions are unversioned compatibility points, re-audit collectSaveData/startGame when upstream save setup changes.
    case "saves": {
        _title = "Campaign Saves";
        if (isNil "A3A_backgroundInitDone" || {isNil "A3A_fnc_collectSaveData"}) then {
            _description = "Antistasi save selection isn't ready yet.";
        } else {
            if (isNil "A3A_saveData") then {
                private _saves = (call A3A_fnc_collectSaveData) select {
                    toLower (_x getOrDefault ["map", ""]) isEqualTo toLower worldName
                };
                if (_saves isEqualTo []) then {
                    _description = "No Antistasi saves were found for this map.";
                } else {
                    private _shown = _saves select [0, (count _saves) min MAX_SAVE_RESULTS];
                    private _lines = _shown apply {
                        private _idValue = _x getOrDefault ["gameID", ""];
                        private _id = if (_idValue isEqualType "") then {_idValue} else {str _idValue};
                        private _name = _x getOrDefault ["name", "Unnamed campaign"];
                        if !(_name isEqualType "" && _name != "") then { _name = "Unnamed campaign" };
                        private _version = _x getOrDefault ["version", "unknown"];
                        format ["- %1 - ID `%2` - version %3", _name, _id, _version]
                    };
                    _description = _lines joinString _newline;
                    if (count _saves > count _shown) then {
                        _description = format ["%1%2...and %3 more.", _description, _newline, count _saves - count _shown];
                    };
                    _fields = [["Map", worldName, true], ["Count", str count _saves, true]];
                };
            } else {
                _description = "Campaign saves can only be listed before a campaign is selected. Restart the Antistasi mission first.";
            };
        };
    };
    case "loadsave": {
        _title = "Campaign Load";
        if (isNil "A3A_backgroundInitDone" || {isNil "A3A_fnc_collectSaveData"} || {isNil "A3A_fnc_startGame"}) then {
            _description = "Antistasi save selection isn't ready yet.";
        } else {
            if (isNil "A3A_saveData") then {
                private _saveId = _options param [0, ""];
                private _matches = (call A3A_fnc_collectSaveData) select {
                    private _idValue = _x getOrDefault ["gameID", ""];
                    private _id = if (_idValue isEqualType "") then {_idValue} else {str _idValue};
                    _id isEqualTo _saveId && {toLower (_x getOrDefault ["map", ""]) isEqualTo toLower worldName}
                };
                if (_matches isEqualTo []) then {
                    _description = format ["No Antistasi save with ID `%1` exists for %2.", _saveId, worldName];
                    _color = EMBED_COLOR_ERROR;
                } else {
                    private _saveData = _matches # 0;
                    _saveData set ["startType", "load"];
                    [_saveData] call A3A_fnc_startGame;
                    private _name = _saveData getOrDefault ["name", "Unnamed campaign"];
                    if !(_name isEqualType "" && _name != "") then { _name = "Unnamed campaign" };
                    _description = format ["Loading **%1** (ID `%2`) on %3.", _name, _saveId, worldName];
                    _color = EMBED_COLOR_SUCCESS;
                };
            } else {
                _description = "A campaign has already been selected. Restart the Antistasi mission before loading a different save.";
            };
        };
    };
    case "save": {
        _title = "Campaign Save";
        if (_ready) then {
            if (isNil "A3A_fnc_saveLoop") then {
                _description = "Antistasi save routine is unavailable.";
                _color = EMBED_COLOR_ERROR;
            } else {
                if (missionNamespace getVariable ["savingServer", false]) then {
                    _description = "A campaign save is already in progress.";
                } else {
                    // ponytail: A3A_fnc_saveLoop contains sleeps and requires a scheduled environment.
                    [] spawn A3A_fnc_saveLoop;
                    _description = "Antistasi campaign save started.";
                };
            };
        } else {
            _description = "Antistasi Ultimate is still starting.";
        };
    };
    case "announce": {
        _title = "Announcement";
        private _message = _options param [0, ""];
        if (_ready) then {
            if (
                _message isEqualType ""
                && _message != ""
                && {count _message <= MAX_ANNOUNCEMENT_LENGTH}
                && {_message find "<" < 0}
                && {_message find ">" < 0}
            ) then {
                ["Petros", _message] remoteExecCall ["A3A_fnc_customHint", 0, false];
                _description = "Announcement sent in-game.";
            } else {
                _description = "Invalid announcement payload.";
                _color = EMBED_COLOR_ERROR;
            };
        } else {
            _description = "Antistasi Ultimate is still starting.";
        };
    };
    default {
        _title = "Unsupported Command";
        _description = "Petros didn't recognize this command.";
        _color = EMBED_COLOR_ERROR;
    };
};

[
    "Petros.complete_interaction",
    [_interactionId, _title, _description, _fields, _color, true]
] call py3_fnc_callExtension;
