#include "../script_component.hpp"
/*
 * Author: Bobby
 * Starts Discord Rich Presence on player clients.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(startRichPresence)
 *
 * Public: No
 */
if (!hasInterface) exitWith {};

private _config = configFile >> "CfgPetrosRichPresence";
if (getNumber (_config >> "enabled") isEqualTo 0) exitWith {};
if (getText (_config >> "applicationID") isEqualTo "") exitWith {
    WARNING("Discord Rich Presence disabled: CfgPetrosRichPresence.applicationID is empty");
};
if (isNil "py3_fnc_callExtension") exitWith {
    WARNING("Discord Rich Presence unavailable: Pythia is not loaded on the client");
};

private _interval = (getNumber (_config >> "updateInterval")) max 15;

[
    { !isNull player && {!isNull findDisplay 46} },
    {
        params ["_interval"];

        call FUNC(updateRichPresence);
        if (isNil QGVAR(richPresencePFH)) then {
            GVAR(richPresencePFH) = [{call FUNC(updateRichPresence)}, _interval] call CBA_fnc_addPerFrameHandler;
        };
        if (isNil QGVAR(richPresenceUnloadEH)) then {
            GVAR(richPresenceUnloadEH) = (findDisplay 46) displayAddEventHandler ["Unload", {call FUNC(stopRichPresence)}];
        };
    },
    [_interval]
] call CBA_fnc_waitUntilAndExecute;
