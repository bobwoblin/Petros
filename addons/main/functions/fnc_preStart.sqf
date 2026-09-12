#include "../script_component.hpp"
/*
 * Author: Bobby
 * Starts the Petros Python bridge on a dedicated server before a mission is loaded.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(preStart)
 *
 * Public: No
 */
if (!isDedicated) exitWith {};

INFO("preStart entered");

private _callExtension = uiNamespace getVariable "PY3_fnc_callExtension";
if (isNil "_callExtension") then {
    _callExtension = missionNamespace getVariable "PY3_fnc_callExtension";
};
if (isNil "_callExtension") exitWith {
    WARNING("Pythia bridge unavailable during preStart");
};

private _health = ["Petros.start"] call _callExtension;
if (_health isEqualType [] && {count _health > 0} && {_health#0}) then {
    INFO("Python started during preStart");
} else {
    ERROR_1("Python preStart failed: %1",_health);
};
