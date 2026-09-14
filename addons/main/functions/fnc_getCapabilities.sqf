#include "../script_component.hpp"
/*
 * Author: Bobby
 * Reports the Antistasi interfaces Petros can safely use at runtime.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * Capability pairs <ARRAY>
 *
 * Example:
 * call FUNC(getCapabilities)
 *
 * Public: No
 */
[
    ["campaign", !isNil "serverInitDone" && {!isNil "A3A_startupState"}],
    ["tasks", !isNil "A3A_tasksData"],
    ["territory", !isNil "markersX" && {!isNil "controlsX"} && {!isNil "sidesX"}],
    ["resources", !isNil "server" && {!isNull server}],
    ["commander", !isNil "theBoss"],
    ["save", !isNil "A3A_saveData"],
    ["events", !isNil "A3A_fnc_addEventHandler"]
]
