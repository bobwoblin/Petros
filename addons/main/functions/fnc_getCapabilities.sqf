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
    ["save", !isNil "A3A_fnc_saveLoop" && {!isNil "savingServer"}],
    ["garrisons", !isNil "A3A_fnc_getGarrison" && {!isNil "A3A_fnc_countGarrison"}],
    ["garage", !isNil "HR_GRG_fnc_getSaveData"],
    ["towns", !isNil "A3A_townData" && {!isNil "citiesX"}],
    ["support", !isNil "supportPoints" && {!isNil "maxSupportPoints"}],
    ["assets", !isNil "HR_GRG_fnc_getSaveData"],
    ["events", !isNil "A3A_fnc_addEventHandler"],
    ["territoryEvents", !isNil "A3A_Events_fnc_addEventListener"]
]
