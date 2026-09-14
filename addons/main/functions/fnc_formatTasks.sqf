#include "../script_component.hpp"
/*
 * Author: Bobby
 * Formats normalized Antistasi tasks for Discord command output.
 *
 * Arguments:
 * 0: Task records <ARRAY>
 * 1: Current server time <NUMBER>
 *
 * Return Value:
 * Display lines <STRING>
 *
 * Example:
 * [["task", "RES", "CREATED", 10], 70] call FUNC(formatTasks)
 *
 * Public: No
 */
params ["_tasks", "_now"];

private _names = createHashMapFromArray [
    ["AS", "Assassination"], ["CON", "Conquest"], ["CONVOY", "Convoy Ambush"],
    ["DES", "Destroy"], ["LOG", "Supply"], ["RES", "Rescue"],
    ["RIV_ATT", "Rival Attack"], ["SUPP", "Support"]
];
private _lines = _tasks apply {
    _x params ["_id", "_type", "_state", "_created"];
    format [
        "%1 — %2 — %3",
        _names getOrDefault [_type, _type],
        toLower _state,
        [(_now - _created) max 0] call FUNC(formatDuration)
    ]
};
_lines joinString toString [10]
