#include "../script_component.hpp"
/*
 * Author: Bobby
 * Clears the local player's Discord Rich Presence.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(stopRichPresence)
 *
 * Public: No
 */
if (!hasInterface) exitWith {};

if !(isNil QGVAR(richPresencePFH)) then {
    [GVAR(richPresencePFH)] call CBA_fnc_removePerFrameHandler;
    GVAR(richPresencePFH) = nil;
};

if !(isNil QGVAR(richPresenceUnloadEH)) then {
    (findDisplay 46) displayRemoveEventHandler ["Unload", GVAR(richPresenceUnloadEH)];
    GVAR(richPresenceUnloadEH) = nil;
};

if !(isNil "py3_fnc_callExtension") then {
    ["Petros.clear_presence"] call py3_fnc_callExtension;
};
