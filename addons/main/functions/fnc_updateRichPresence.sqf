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

private _config = missionNamespace getVariable [QGVAR(richPresenceConfig), []];
if (_config isEqualTo []) exitWith {};
_config params ["_applicationID", "_interval", "_details", "_largeImage", "_largeText", "_smallImage", "_smallText"];

private _mapName = getText (configFile >> "CfgWorlds" >> worldName >> "description");
if (_mapName isEqualTo "") then {
    _mapName = worldName;
};

private _snapshot = call FUNC(getSnapshot);
private _playerCount = _snapshot get "playerCount";
private _maxPlayers = getNumber (missionConfigFile >> "Header" >> "maxPlayers");
if (_maxPlayers <= 0) then {
    _maxPlayers = _playerCount max count playableUnits;
};

private _state = if (_maxPlayers > 0) then {
    format ["%1 • %2/%3 players", _mapName, _playerCount, _maxPlayers]
} else {
    _mapName
};

private _war = _snapshot get "warLevel";
if (_war >= 0) then {
    _state = _state + format [" • War %1", _war];
};
_state = _state + format [" • %1", side group player];
if (serverName isNotEqualTo "") then {
    _details = if (_details isEqualTo "") then {serverName} else {format ["%1 • %2", serverName, _details]};
};

private _result = [
    "Petros.update_presence",
    [
        _applicationID,
        _details,
        _state,
        _playerCount,
        _maxPlayers,
        _largeImage,
        _largeText,
        _smallImage,
        _smallText
    ]
] call py3_fnc_callExtension;

if (_result isEqualType false && {!_result}) then {
    if !(missionNamespace getVariable [QGVAR(richPresenceWarned), false]) then {
        WARNING("Discord Rich Presence disabled: invalid application ID or player counts; correct server config.local.py and restart");
        GVAR(richPresenceWarned) = true;
    };
    call FUNC(stopRichPresence);
} else {
    GVAR(richPresenceWarned) = false;
};
