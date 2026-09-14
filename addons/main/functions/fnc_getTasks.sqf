#include "../script_component.hpp"
/*
 * Author: Bobby
 * Normalizes Antistasi's centralized task records for the Petros bridge.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * Task records [id, type, state, created] <ARRAY>
 *
 * Example:
 * call FUNC(getTasks)
 *
 * Public: No
 */
// ponytail: A3A_tasksData is explicitly non-public upstream; this adapter is the replacement point if its four-field record changes.
private _tasks = missionNamespace getVariable ["A3A_tasksData", []];
_tasks select {
    _x isEqualType [] && {count _x >= 4} &&
    {(_x # 0) isEqualType ""} && {(_x # 1) isEqualType ""} &&
    {(_x # 2) isEqualType ""} && {(_x # 3) isEqualType 0}
} apply {[_x # 0, _x # 1, _x # 2, _x # 3]}
