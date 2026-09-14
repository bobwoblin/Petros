#include "../script_component.hpp"
/*
 * Author: Bobby
 * Sends one authoritative Antistasi marker ownership event to reconciliation.
 *
 * Arguments:
 * 0: Marker name <STRING>
 * 1: Winning side <SIDE>
 *
 * Return Value:
 * None
 *
 * Example:
 * ["airport_1", teamPlayer] call FUNC(handleTerritoryEvent)
 *
 * Public: No
 */
params ["_marker", "_winner"];
if (!isServer || {isNil "py3_fnc_callExtension"} || {!(_marker isEqualType "")}) exitWith {};

private _known = (missionNamespace getVariable ["markersX", []]) - ["Synd_HQ"];
if !(_marker in _known) exitWith {};
private _location = [_marker] call FUNC(getLocation);
["Petros.observe_territory", [[_marker, _location # 0, _location # 1, _location # 2, _location # 3]]] call py3_fnc_callExtension;
