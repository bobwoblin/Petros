#include "../script_component.hpp"
/*
 * Author: Bobby
 * Normalizes Antistasi's public garage save snapshot and strategic asset classes.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * [garage categories, strategic asset categories] <ARRAY>
 *
 * Example:
 * call FUNC(getGarage)
 *
 * Public: No
 */
if (isNil "HR_GRG_fnc_getSaveData") exitWith {[]};

private _saveData = call HR_GRG_fnc_getSaveData;
if !(_saveData isEqualType [] && {count _saveData >= 1}) exitWith {[]};
private _garage = _saveData # 0;
if !(_garage isEqualType [] && {count _garage >= 8}) exitWith {[]};

private _definitions = [
    ["undercover", "Undercover Vehicles"], ["vehicles", "Vehicles"],
    ["armor", "Armor"], ["helicopters", "Helicopters"],
    ["aircraft", "Aircraft"], ["boats", "Boats"],
    ["sources", "Service Vehicles"], ["statics", "Statics"]
];
private _categories = [];
private _assetMaps = createHashMapFromArray (
    ["armor", "apcs", "aa", "artillery", "helicopters", "aircraft", "statics", "transports"]
    apply {[_x, createHashMap]}
);

{
    _x params ["_key", "_label"];
    private _items = _garage param [_forEachIndex, createHashMap];
    if !(_items isEqualType createHashMap) then {_items = createHashMap};
    private _classes = createHashMap;
    {
        private _record = _y;
        if (_record isEqualType [] && {count _record >= 2}) then {
            private _name = _record param [0, "Unknown vehicle"];
            private _class = _record param [1, ""];
            if !(_name isEqualType "") then {_name = "Unknown vehicle"};
            if (_class isEqualType "" && _class != "") then {
                private _current = _classes getOrDefault [_class, [_name, 0]];
                _current set [1, (_current # 1) + 1];
                _classes set [_class, _current];

                private _config = configFile >> "CfgVehicles" >> _class;
                private _threat = getArray (_config >> "threat");
                private _antiAir = count _threat >= 3 && {_threat # 2 >= 0.5};
                private _asset = switch (true) do {
                    case (_class isKindOf "Helicopter"): {"helicopters"};
                    case (_class isKindOf "Plane"): {"aircraft"};
                    case (_class isKindOf "StaticAAWeapon" || _antiAir): {"aa"};
                    case (_class isKindOf "StaticMortar" || {_class isKindOf "StaticCannon"} || {getNumber (_config >> "artilleryScanner") > 0}): {"artillery"};
                    case (_class isKindOf "Wheeled_APC_F" || {_class isKindOf "Tracked_APC_F"}): {"apcs"};
                    case (_class isKindOf "Tank"): {"armor"};
                    case (_class isKindOf "StaticWeapon"): {"statics"};
                    case (_class isKindOf "LandVehicle" || {_class isKindOf "Ship"}): {"transports"};
                    default {""};
                };
                if (_asset != "") then {
                    private _assets = _assetMaps get _asset;
                    private _assetRow = _assets getOrDefault [_class, [_name, 0]];
                    _assetRow set [1, (_assetRow # 1) + 1];
                    _assets set [_class, _assetRow];
                };
            };
        };
    } forEach _items;
    private _rows = keys _classes apply {
        private _row = _classes get _x;
        [_row # 0, _x, _row # 1]
    };
    _rows sort true;
    _categories pushBack [_key, _label, count _items, _rows];
} forEach _definitions;

private _assets = [];
{
    _x params ["_key", "_label"];
    private _items = _assetMaps get _key;
    private _rows = keys _items apply {
        private _row = _items get _x;
        [_row # 0, _x, _row # 1]
    };
    _rows sort true;
    private _total = 0;
    {_total = _total + (_x # 2)} forEach _rows;
    _assets pushBack [_key, _label, _total, _rows];
} forEach [
    ["armor", "Armor"], ["apcs", "APCs / IFVs"], ["aa", "AA"],
    ["artillery", "Artillery"], ["helicopters", "Helicopters"],
    ["aircraft", "Aircraft"], ["statics", "Armed Statics"], ["transports", "Transports"]
];

[_categories, _assets]
