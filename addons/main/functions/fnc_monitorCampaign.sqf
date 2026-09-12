#include "../script_component.hpp"
/*
 * Author: Bobby
 * Emits Discord events for Antistasi territory ownership and War Level changes.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(monitorCampaign)
 *
 * Public: No
 */
if (!isServer || {isNil "py3_fnc_callExtension"}) exitWith {};

private _owners = missionNamespace getVariable [QGVAR(territoryOwners), createHashMap];
private _lastWar = missionNamespace getVariable [QGVAR(lastWarLevel), -1];
private _current = markersX - controlsX - ["Synd_HQ"];

{
    private _newSide = sidesX getVariable [_x, sideUnknown];
    private _oldSide = _owners getOrDefault [_x, _newSide];
    if (_newSide isNotEqualTo _oldSide && {_newSide isNotEqualTo sideUnknown}) then {
        private _location = [_x] call FUNC(getLocation);
        private _fields = [
            ["Location", _location # 0, true],
            ["Type", _location # 1, true],
            ["Grid", _location # 3, true]
        ];
        if (_newSide isEqualTo teamPlayer) then {
            [
                "Petros.send_event",
                ["territory_gain", "Resistance control established.", _fields]
            ] call py3_fnc_callExtension;
        } else {
            if (_oldSide isEqualTo teamPlayer) then {
                _fields pushBack ["New Owner", _location # 2, true];
                [
                    "Petros.send_event",
                    ["territory_loss", "Resistance control lost.", _fields]
                ] call py3_fnc_callExtension;
            };
        };
    };
    _owners set [_x, _newSide];
} forEach _current;

{if !(_x in _current) then {_owners deleteAt _x}} forEach keys _owners;

private _war = missionNamespace getVariable ["tierWar", -1];
if (_lastWar >= 0 && _war > _lastWar) then {
    [
        "Petros.send_event",
        [
            "war_increase",
            "The campaign War Level increased.",
            [["Previous", str _lastWar, true], ["Current", str _war, true]]
        ]
    ] call py3_fnc_callExtension;
};

missionNamespace setVariable [QGVAR(territoryOwners), _owners];
missionNamespace setVariable [QGVAR(lastWarLevel), _war];
