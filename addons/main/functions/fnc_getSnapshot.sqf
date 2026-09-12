#include "../script_component.hpp"
/*
 * Author: Bobby
 * Captures the current Antistasi server state used by Discord commands.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * Current campaign/server snapshot <HASHMAP>
 *
 * Example:
 * call FUNC(getSnapshot)
 *
 * Public: No
 */
// ponytail: Antistasi Ultimate mission globals aren't a versioned public API, re-audit these names when upstream changes initServer/initZones/saveLoop/task state.
private _ready = (missionNamespace getVariable ["serverInitDone", false]) &&
    {(missionNamespace getVariable ["A3A_startupState", ""]) isEqualTo "completed"};
private _humans = allPlayers - entities "HeadlessClient_F";
private _players = _humans apply {name _x};
private _commander = "None";
private _boss = missionNamespace getVariable ["theBoss", objNull];
if (!isNull _boss) then {_commander = name _boss};

private _war = missionNamespace getVariable ["tierWar", -1];
private _serverObject = missionNamespace getVariable ["server", objNull];
private _resources = if (isNull _serverObject) then {-1} else {_serverObject getVariable ["resourcesFIA", -1]};
private _hr = if (isNull _serverObject) then {-1} else {_serverObject getVariable ["hr", -1]};
private _territory = [];
private _strategicTotal = 0;
private _strategicOwned = 0;

{
    _x params ["_variable", "_label"];
    private _markers = missionNamespace getVariable [_variable, []];
    private _owned = 0;
    if (!isNil "teamPlayer" && {!isNil "sidesX"}) then {
        _owned = {sidesX getVariable [_x, sideUnknown] isEqualTo teamPlayer} count _markers;
    };
    _territory pushBack [_label, _owned, count _markers];
    _strategicOwned = _strategicOwned + _owned;
    _strategicTotal = _strategicTotal + count _markers;
} forEach [
    ["citiesX", "Towns"],
    ["outposts", "Outposts"],
    ["milbases", "Military Bases"],
    ["airportsX", "Airports"],
    ["resourcesX", "Resources"],
    ["factories", "Factories"],
    ["seaports", "Seaports"]
];

private _active = missionNamespace getVariable ["A3A_activeTasks", []];
private _missions = _active apply {if (_x isEqualType "") then {_x} else {str _x}};

createHashMapFromArray [
    ["ready", _ready],
    ["map", worldName],
    ["fps", round (diag_fps * 10) / 10],
    ["uptime", floor serverTime],
    ["players", _players],
    ["playerCount", count _humans],
    ["commander", _commander],
    ["warLevel", _war],
    ["resources", _resources],
    ["hr", _hr],
    ["strategicOwned", _strategicOwned],
    ["strategicTotal", _strategicTotal],
    ["territory", _territory],
    ["missions", _missions],
    ["version", missionNamespace getVariable ["A3A_serverVersion", "Unknown"]]
]
