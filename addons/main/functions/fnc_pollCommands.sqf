#include "../script_component.hpp"
/*
 * Author: Bobby
 * Drains queued Discord commands from Pythia and dispatches them in mission context.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(pollCommands)
 *
 * Public: No
 */
if (!isServer || {isNil "py3_fnc_callExtension"}) exitWith {};

private _saving = missionNamespace getVariable ["savingServer", false];
private _lastSaving = missionNamespace getVariable [QGVAR(lastSavingState), objNull];
if (not (_lastSaving isEqualType true && _lastSaving isEqualTo _saving)) then {
    missionNamespace setVariable [QGVAR(lastSavingState), _saving];
    ["Petros.observe_save", [_saving]] call py3_fnc_callExtension;
};

private _commands = ["Petros.drain_commands", [10]] call py3_fnc_callExtension;
if !(_commands isEqualType []) exitWith {};

{_x call FUNC(handleCommand)} forEach _commands;
