#include "../script_component.hpp"
/*
 * Author: Bobby
 * Resolves an Antistasi marker into the display data used by Discord responses.
 *
 * Arguments:
 * 0: Marker name <STRING>
 *
 * Return Value:
 * Location data [name, type, owner, grid, marker] <ARRAY>
 *
 * Example:
 * ["airport_1"] call FUNC(getLocation)
 *
 * Public: No
 */
params ["_marker"];

private _name = markerText _marker;
if (!isNil "A3A_fnc_localizar") then {
    private _localized = [_marker] call A3A_fnc_localizar;
    if (_localized isEqualType "" && _localized != "") then { _name = _localized };
};
if (_name == "") then { _name = _marker };

private _type = "Location";
{
    _x params ["_variable", "_label"];
    if (_marker in (missionNamespace getVariable [_variable, []])) exitWith { _type = _label };
} forEach [
    ["citiesX", "Town"],
    ["outposts", "Outpost"],
    ["milbases", "Military Base"],
    ["airportsX", "Airport"],
    ["resourcesX", "Resource"],
    ["factories", "Factory"],
    ["seaports", "Seaport"]
];

private _side = sideUnknown;
if (!isNil "sidesX") then { _side = sidesX getVariable [_marker, sideUnknown] };

private _owner = "Unknown";
if (!isNil "teamPlayer") then {
    if (_side isEqualTo teamPlayer) then { _owner = "Resistance" };
};
if (!isNil "Occupants") then {
    if (_side isEqualTo Occupants) then { _owner = "Occupants" };
};
if (!isNil "Invaders") then {
    if (_side isEqualTo Invaders) then { _owner = "Invaders" };
};
if (_side isEqualTo civilian) then { _owner = "Civilian" };

[_name, _type, _owner, mapGridPosition (getMarkerPos _marker), _marker]
