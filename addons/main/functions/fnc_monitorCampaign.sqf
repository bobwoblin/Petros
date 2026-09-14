#include "../script_component.hpp"
/*
 * Author: Bobby
 * Sends the current Antistasi read model to the Python transition tracker.
 *
 * Arguments:
 * None
 *
 * Return Value:
 * None
 *
 * Example:
 * call FUNC(monitorCampaign)
 *
 * Public: No
 */
if (!isServer || {isNil "py3_fnc_callExtension"}) exitWith {};

private _snapshot = call FUNC(getSnapshot);
private _payload = keys _snapshot apply {[_x, _snapshot get _x]};
["Petros.observe_campaign", [_payload]] call py3_fnc_callExtension;
