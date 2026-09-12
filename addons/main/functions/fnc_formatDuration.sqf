#include "../script_component.hpp"
/*
 * Author: Bobby
 * Formats a duration for compact Discord status output.
 *
 * Arguments:
 * 0: Duration in seconds <NUMBER>
 *
 * Return Value:
 * Formatted hours/minutes <STRING>
 *
 * Example:
 * [3700] call FUNC(formatDuration)
 *
 * Public: No
 */
params [["_seconds", 0, [0]]];

private _hours = floor (_seconds / 3600);
private _minutes = floor ((_seconds mod 3600) / 60);
format ["%1h %2m", _hours, _minutes]
