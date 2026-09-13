#include "../script_component.hpp"
/*
 * Author: Bobby
 * Initializes Antistasi event tracking after the campaign has finished startup.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(startMonitoring)
 *
 * Public: No
 */
if (!isServer || {missionNamespace getVariable [QGVAR(monitoringStarted), false]}) exitWith {};
missionNamespace setVariable [QGVAR(monitoringStarted), true];

private _strategic = markersX - controlsX - ["Synd_HQ"];
private _owners = createHashMap;
{_owners set [_x, sidesX getVariable [_x, sideUnknown]]} forEach _strategic;
missionNamespace setVariable [QGVAR(territoryOwners), _owners];

private _lastWar = missionNamespace getVariable ["tierWar", -1];
missionNamespace setVariable [QGVAR(lastWarLevel), _lastWar];

addMissionEventHandler ["PlayerConnected", {
    params ["_id", "_uid", "_name"];
    if (_uid == "" || _name == "__SERVER__" || {_uid select [0, 2] == "HC"}) exitWith {};
    if (!isNil "py3_fnc_callExtension") then {
        [
            "Petros.send_event",
            ["player_join", format ["%1 joined the server.", _name], [["Player", _name, true]]]
        ] call py3_fnc_callExtension;
    };
}];

addMissionEventHandler ["PlayerDisconnected", {
    params ["_id", "_uid", "_name"];
    if (_uid == "" || _name == "__SERVER__" || {_uid select [0, 2] == "HC"}) exitWith {};
    if (!isNil "py3_fnc_callExtension") then {
        [
            "Petros.send_event",
            ["player_leave", format ["%1 left the server.", _name], [["Player", _name, true]]]
        ] call py3_fnc_callExtension;
    };
}];

["Petros.send_event", ["server_online", "", [
    ["Map", worldName, true],
    ["War Level", str _lastWar, true],
    ["Players", str (count (allPlayers - entities "HeadlessClient_F")), true]
]]] call py3_fnc_callExtension;

call FUNC(monitorCampaign);

GVAR(campaignMonitorPFH) = [{call FUNC(monitorCampaign)}, CAMPAIGN_MONITOR_INTERVAL] call CBA_fnc_addPerFrameHandler;
