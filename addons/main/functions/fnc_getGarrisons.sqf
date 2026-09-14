#include "../script_component.hpp"
/*
 * Author: Bobby
 * Normalizes player-owned Antistasi garrisons for read-only presentation.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * Garrison rows [marker, name, type, owner, total, cargo, crew, vehicles, limit] <ARRAY>
 *
 * Example:
 * call FUNC(getGarrisons)
 *
 * Public: No
 */
if (
    isNil "A3A_fnc_getGarrison"
    || {isNil "A3A_fnc_countGarrison"}
    || {isNil "teamPlayer"}
    || {isNil "sidesX"}
) exitWith {[]};

private _markers = (missionNamespace getVariable ["markersX", []])
    - (missionNamespace getVariable ["controlsX", []])
    - ["Synd_HQ"];
private _rows = [];

{
    if (sidesX getVariable [_x, sideUnknown] isEqualTo teamPlayer) then {
        private _location = [_x] call FUNC(getLocation);
        private _counts = [[_x] call A3A_fnc_getGarrison, false] call A3A_fnc_countGarrison;
        private _limit = -1;
        // ponytail: garrison limits are exposed only by an unversioned upstream helper, re-audit A3A_fnc_getGarrisonLimit when its public contract changes.
        if !(isNil "A3A_fnc_getGarrisonLimit") then {
            _limit = [_x] call A3A_fnc_getGarrisonLimit;
        };
        _counts params ["_vehicles", "_crew", "_cargo"];
        _rows pushBack [
            _x, _location # 0, _location # 1, _location # 2,
            _vehicles + _crew + _cargo, _cargo, _crew, _vehicles, _limit
        ];
    };
} forEach _markers;

_rows
