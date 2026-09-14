// Run locally after normal Arma/CBA initialization with Petros and Pythia loaded.
private _failures = [];
private _check = {
    params ["_name", "_ok"];
    diag_log format ["[petros][TEST] %1 %2", ["FAIL", "PASS"] select _ok, _name];
    if (!_ok) then {_failures pushBack _name};
};

["patch petros_main exists", isClass (configFile >> "CfgPatches" >> "petros_main")] call _check;
{
    [format ["function %1 exists", _x], !(isNil _x)] call _check;
} forEach [
    "petros_fnc_preStart",
    "petros_fnc_formatDuration",
    "petros_fnc_getCapabilities",
    "petros_fnc_getLocation",
    "petros_fnc_getSnapshot",
    "petros_fnc_formatTasks",
    "petros_fnc_getTasks",
    "petros_fnc_handleCommand",
    "petros_fnc_monitorCampaign",
    "petros_fnc_pollCommands",
    "petros_fnc_postInit",
    "petros_fnc_startMonitoring",
    "petros_fnc_startRichPresence",
    "petros_fnc_stopRichPresence",
    "petros_fnc_updateRichPresence"
];

private _capabilities = call petros_fnc_getCapabilities;
["Antistasi capabilities are reported", _capabilities isEqualType [] && {count _capabilities >= 6}] call _check;
private _tasks = call petros_fnc_getTasks;
["Antistasi task adapter returns an array", _tasks isEqualType []] call _check;

["public rich presence config received", !(isNil "petros_richPresenceConfig") && {petros_richPresenceConfig isEqualType []}] call _check;

private _preStart = configFile >> "CfgFunctions" >> "petros" >> "Bootstrap" >> "preStart";
["preStart remains engine-registered", getNumber (_preStart >> "preStart") == 1] call _check;

diag_log format ["[petros][TEST] COMPLETE failures=%1", count _failures];
_failures
