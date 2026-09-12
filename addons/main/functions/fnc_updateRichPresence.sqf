#include "../script_component.hpp"
/*
 * Author: Bobby
 * Updates the local player's Discord Rich Presence.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(updateRichPresence)
 *
 * Public: No
 */
if (!hasInterface || {isNil "py3_fnc_callExtension"}) exitWith {};

private _config = configFile >> "CfgPetrosRichPresence";
private _applicationID = getText (_config >> "applicationID");
if (_applicationID isEqualTo "") exitWith {};

private _mapName = getText (configFile >> "CfgWorlds" >> worldName >> "description");
if (_mapName isEqualTo "") then {
    _mapName = worldName;
};

private _playerCount =
    playersNumber west +
    playersNumber east +
    playersNumber resistance +
    playersNumber civilian;
private _maxPlayers = getNumber (missionConfigFile >> "Header" >> "maxPlayers");
if (_maxPlayers <= 0) then {
    _maxPlayers = _playerCount max count playableUnits;
};

private _state = if (_maxPlayers > 0) then {
    format ["%1 • %2/%3 players", _mapName, _playerCount, _maxPlayers]
} else {
    _mapName
};

private _result = [
    "Petros.update_presence",
    [
        _applicationID,
        getText (_config >> "details"),
        _state,
        _playerCount,
        _maxPlayers,
        getText (_config >> "largeImageKey"),
        getText (_config >> "largeImageText")
    ]
] call py3_fnc_callExtension;

if (_result isEqualType false && {!_result}) then {
    if !(missionNamespace getVariable [QGVAR(richPresenceWarned), false]) then {
        WARNING("Discord Rich Presence could not connect to the local Discord desktop client");
        GVAR(richPresenceWarned) = true;
    };
} else {
    GVAR(richPresenceWarned) = false;
};
