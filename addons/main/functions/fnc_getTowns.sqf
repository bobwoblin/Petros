#include "../script_component.hpp"
/*
 * Author: Bobby
 * Normalizes the town political state Antistasi exposes in its player map UI.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * Town rows [marker, name, population, rebel support, government support, owner] <ARRAY>
 *
 * Example:
 * call FUNC(getTowns)
 *
 * Public: No
 */
if (isNil "A3A_townData" || {isNil "citiesX"}) exitWith {[]};

// ponytail: A3A_townData's [population, vehicles, government, rebel] record is unversioned, re-audit when upstream replaces the town-data map.
private _rows = [];
{
    private _data = A3A_townData getOrDefault [_x, []];
    if (_data isEqualType [] && {count _data >= 4}) then {
        private _location = [_x] call FUNC(getLocation);
        _rows pushBack [
            _x, _location # 0, round (_data # 0),
            round (_data # 3), round (_data # 2), _location # 2
        ];
    };
} forEach citiesX;

_rows
