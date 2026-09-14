#include "../script_component.hpp"
/*
 * Author: Bobby
 * Handles concrete read-only intelligence commands and the safe restart workflow.
 *
 * Arguments:
 * 0: Discord interaction identifier <STRING>
 * 1: Command name <STRING>
 * 2: Validated command options <ARRAY>
 *
 * Return Value:
 * True when the command was handled <BOOL>
 *
 * Example:
 * ["123", "economy", []] call FUNC(handleIntelCommand)
 *
 * Public: No
 */
params ["_interactionId", "_command", ["_options", []]];
private _supported = ["garrisons", "garage", "towns", "economy", "assets", "restart", "__restart_notice", "__restart_save", "__restart_failed"];
if !(_command in _supported) exitWith {false};

private _snapshot = call FUNC(getSnapshot);
private _ready = _snapshot get "ready";
private _capabilities = createHashMapFromArray (_snapshot get "capabilities");
private _title = "Petros";
private _description = "";
private _fields = [];
private _color = EMBED_COLOR_DEFAULT;
private _newline = toString [10];

switch (_command) do {
    case "garrisons": {
        _title = "Resistance Garrisons";
        private _rows = if (_ready) then {call FUNC(getGarrisons)} else {[]};
        if (not _ready) then {_description = "Antistasi Ultimate is still starting."} else {
            if (not (_capabilities getOrDefault ["garrisons", false])) then {
                _description = "Garrison intelligence is unsupported by this Antistasi version.";
                _color = EMBED_COLOR_ERROR;
            } else {
                private _marker = _options param [0, ""];
                private _matches = _rows select {_x # 0 == _marker};
                if (_marker != "" && {_matches isEqualTo []}) then {
                    _description = "That player-owned strategic location is unavailable.";
                    _color = EMBED_COLOR_ERROR;
                } else {
                    if (_marker != "") then {
                        (_matches # 0) params ["_ignoredMarker", "_name", "_type", "_owner", "_total", "_cargo", "_crew", "_vehicles", "_limit"];
                        _title = format ["%1 Garrison", _name];
                        _fields = [["Type", _type, true], ["Owner", _owner, true], ["Total", str _total, true], ["Infantry / cargo", str _cargo, true], ["Vehicle crew", str _crew, true], ["Vehicles", str _vehicles, true], ["Capacity", [str _limit, "Unlimited"] select (_limit < 0), true]];
                    } else {
                        private _sorted = _rows apply {[-(_x # 4), _x]};
                        _sorted sort true;
                        private _shown = _sorted select [0, (count _sorted) min MAX_INTEL_RESULTS];
                        _description = (_shown apply {
                            private _row = _x # 1;
                            format ["- **%1** (%2): %3 total · %4 inf · %5 crew · %6 veh", _row # 1, _row # 2, _row # 4, _row # 5, _row # 6, _row # 7]
                        }) joinString _newline;
                        if (_description == "") then {_description = "No player-owned strategic garrisons were found."};
                        _fields = [["Locations", str count _rows, true]];
                    };
                };
            };
        };
    };
    case "garage": {
        _title = "Garage Inventory";
        private _data = if (_ready) then {call FUNC(getGarage)} else {[]};
        if (not _ready) then {_description = "Antistasi Ultimate is still starting."} else {
            if (_data isEqualTo []) then {
                _description = "Garage inventory is unsupported by this Antistasi version.";
                _color = EMBED_COLOR_ERROR;
            } else {
                private _category = _options param [0, ""];
                private _rows = (_data # 0) select {_category == "" || {_x # 0 == _category}};
                if (_rows isEqualTo []) then {_description = "That garage category is unavailable."; _color = EMBED_COLOR_ERROR} else {
                    if (_category == "") then {
                        _fields = _rows apply {[_x # 1, str (_x # 2), true]};
                        _description = "Stored vehicle counts. Antistasi's public snapshot does not expose reliable checkout state.";
                    } else {
                        private _row = _rows # 0;
                        private _shown = (_row # 3) select [0, (count (_row # 3)) min MAX_INTEL_RESULTS];
                        _description = (_shown apply {format ["- **%1** ×%3 (`%2`)", _x # 0, _x # 1, _x # 2]}) joinString _newline;
                        if (_description == "") then {_description = "No stored vehicles in this category."};
                        _fields = [["Category", _row # 1, true], ["Stored", str (_row # 2), true]];
                    };
                };
            };
        };
    };
    case "towns": {
        _title = "Town Support";
        private _rows = if (_ready) then {call FUNC(getTowns)} else {[]};
        if (not _ready) then {_description = "Antistasi Ultimate is still starting."} else {
            if (not (_capabilities getOrDefault ["towns", false])) then {
                _description = "Town support is unsupported by this Antistasi version.";
                _color = EMBED_COLOR_ERROR;
            } else {
                private _sort = _options param [0, "lowest"];
                if (_sort == "owned") then {_rows = _rows select {_x # 5 == "Resistance"}};
                if (_sort == "unowned") then {_rows = _rows select {_x # 5 != "Resistance"}};
                private _sorted = _rows apply {[
                    switch (_sort) do {case "highest": {-(_x # 3)}; case "population": {-(_x # 2)}; default {_x # 3}}, _x
                ]};
                _sorted sort true;
                private _shown = _sorted select [0, (count _sorted) min MAX_INTEL_RESULTS];
                _description = (_shown apply {
                    private _row = _x # 1;
                    format ["- **%1**: %2 pop · %3%% rebel · %4%% government · %5", _row # 1, _row # 2, _row # 3, _row # 4, _row # 5]
                }) joinString _newline;
                if (_description == "") then {_description = "No matching towns were found."};
                _fields = [["Towns", str count _rows, true], ["Order", _sort, true]];
            };
        };
    };
    case "economy": {
        _title = "Campaign Economy";
        if (not _ready) then {_description = "Antistasi Ultimate is still starting."} else {
            _fields = [["Resources", str (_snapshot get "resources"), true], ["HR", str (_snapshot get "hr"), true], ["War Level", str (_snapshot get "warLevel"), true]];
            if (_capabilities getOrDefault ["support", false]) then {
                _fields pushBack ["Support Points", format ["%1 / %2", _snapshot get "supportPoints", _snapshot get "maxSupportPoints"], true];
            };
            {if ((_x # 0) in ["Factories", "Resources", "Seaports", "Airports"]) then {_fields pushBack [_x # 0, format ["%1 / %2", _x # 1, _x # 2], true]}} forEach (_snapshot get "territory");
            _description = "Authoritative current values; no predicted-income calculation.";
        };
    };
    case "assets": {
        _title = "Strategic Assets";
        private _data = if (_ready) then {call FUNC(getGarage)} else {[]};
        if (not _ready) then {_description = "Antistasi Ultimate is still starting."} else {
            if (_data isEqualTo []) then {_description = "Strategic asset inventory is unsupported by this Antistasi version."; _color = EMBED_COLOR_ERROR} else {
                _fields = (_data # 1) apply {[_x # 1, str (_x # 2), true]};
                private _available = (_data # 1) select {_x # 2 > 0};
                _description = (_available apply {
                    private _examples = (_x # 3) select [0, (count (_x # 3)) min 3];
                    format ["- **%1:** %2", _x # 1, (_examples apply {format ["%1 ×%2", _x # 0, _x # 2]}) joinString ", "]
                }) joinString _newline;
                if (_description == "") then {_description = "No classified strategic assets are stored."};
            };
        };
    };
    case "restart": {
        _title = "Safe Mission Restart";
        private _countdown = _options param [0, 60];
        if (not _ready || {isNil "A3A_fnc_saveLoop"}) then {_description = "Antistasi save support is not ready."; _color = EMBED_COLOR_ERROR} else {
            private _accepted = ["Petros.schedule_restart", [_countdown]] call py3_fnc_callExtension;
            if (_accepted) then {
                private _when = ["now", format ["in %1 seconds", _countdown]] select (_countdown > 0);
                ["Petros", format ["Server restart planned %1. The campaign will save first.", _when]] remoteExecCall ["A3A_fnc_customHint", 0, false];
                _description = format ["Restart scheduled %1. Petros will require an observed Antistasi save start and completion before fixed `#restart`.", _when];
                _color = EMBED_COLOR_SUCCESS;
            } else {_description = "Restart was not scheduled. RCon may be unconfigured or another restart is active."; _color = EMBED_COLOR_ERROR};
        };
    };
    case "__restart_notice": {
        private _seconds = _options param [0, -1];
        if (_seconds in [300, 60, 30, 10]) then {["Petros", format ["Server restart in %1 seconds. A campaign save will run first.", _seconds]] remoteExecCall ["A3A_fnc_customHint", 0, false]};
    };
    case "__restart_save": {
        if (_ready && {!isNil "A3A_fnc_saveLoop"} && {!(missionNamespace getVariable ["savingServer", false])}) then {
            [] spawn A3A_fnc_saveLoop;
        } else {
            ["Petros.restart_save_rejected"] call py3_fnc_callExtension;
        };
    };
    case "__restart_failed": {
        ["Petros", "Scheduled restart cancelled because the campaign save could not be verified."] remoteExecCall ["A3A_fnc_customHint", 0, false];
    };
};

if (_interactionId != "") then {
    ["Petros.complete_interaction", [_interactionId, _title, _description, _fields, _color, true]] call py3_fnc_callExtension;
};
true
