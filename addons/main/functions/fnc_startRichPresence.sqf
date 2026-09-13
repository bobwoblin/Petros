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

[
    { !isNil QGVAR(richPresenceConfig) && {!isNull player} && {!isNull findDisplay 46} && {!isNil "py3_fnc_callExtension"} },
    {
        private _config = GVAR(richPresenceConfig);
        if (_config isEqualTo []) exitWith {};
        if !(_config isEqualType [] && {count _config isEqualTo 7} &&
            {(_config # 1) isEqualType 0} && {(_config # 1) >= 15} && {(_config # 1) <= 300} &&
            {[0, 2, 3, 4, 5, 6] findIf {!((_config # _x) isEqualType "")} isEqualTo -1}) exitWith {
            WARNING("Discord Rich Presence disabled: invalid public settings from server config.local.py");
        };
        private _interval = _config # 1;

        if (isNil QGVAR(richPresencePFH)) then {
            GVAR(richPresencePFH) = [{call FUNC(updateRichPresence)}, _interval] call CBA_fnc_addPerFrameHandler;
        };
        if (isNil QGVAR(richPresenceUnloadEH)) then {
            GVAR(richPresenceUnloadEH) = (findDisplay 46) displayAddEventHandler ["Unload", {call FUNC(stopRichPresence)}];
        };
        call FUNC(updateRichPresence);
    }
] call CBA_fnc_waitUntilAndExecute;
