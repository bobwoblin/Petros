#include "../script_component.hpp"
/*
 * Author: Bobby
 * Starts the mission-side Pythia bridge and campaign monitoring on the server.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(postInit)
 *
 * Public: No
 */
if (hasInterface) then {
    call FUNC(startRichPresence);
};

if (!isServer) exitWith {};

INFO("postInit entered");
if (isNil "py3_fnc_callExtension") exitWith {
    WARNING("Pythia bridge unavailable during postInit");
};

private _health = ["Petros.start"] call py3_fnc_callExtension;
// Only the explicitly public player settings leave the server's config.local.py.
GVAR(richPresenceConfig) = ["Petros.get_presence_config"] call py3_fnc_callExtension;
publicVariable QGVAR(richPresenceConfig);

if !(_health isEqualType [] && {count _health > 0} && {_health # 0}) exitWith {
    ERROR_1("Python postInit failed: %1",_health);
};

["Petros.set_bot_presence"] call py3_fnc_callExtension;

private _missions = [];
{
    if ((configName _x) find "Antistasi_" isEqualTo 0) then {
        private _directory = getText (_x >> "directory");
        private _parts = _directory splitString "\\/";
        if (_parts isNotEqualTo []) then {
            _missions pushBackUnique (_parts # ((count _parts) - 1));
        };
    };
} forEach ("true" configClasses (configFile >> "CfgMissions" >> "MPMissions"));
["Petros.set_missions", [_missions]] call py3_fnc_callExtension;

if (isNil QGVAR(commandPollPFH)) then {
    GVAR(commandPollPFH) = [{call FUNC(pollCommands)}, COMMAND_POLL_INTERVAL] call CBA_fnc_addPerFrameHandler;
};

// Antistasi publishes initialization through its supported CBA event wrapper.
if !(isNil "A3A_fnc_addEventHandler") then {
    ["A3A_event_serverInitDone", {call FUNC(startMonitoring)}] call A3A_fnc_addEventHandler;
};

[
    {
        (missionNamespace getVariable ["serverInitDone", false]) &&
        {(missionNamespace getVariable ["A3A_startupState", ""]) isEqualTo "completed"}
    },
    {call FUNC(startMonitoring)}
] call CBA_fnc_waitUntilAndExecute;

INFO("Mission command bridge started");
