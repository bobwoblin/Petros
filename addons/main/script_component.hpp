#define COMPONENT main
#define COMPONENT_BEAUTIFIED Main
#define COMPONENT_NAME "Petros"
#include "\x\petros\addons\main\script_mod.hpp"

#include "\x\petros\addons\main\script_macros.hpp"

// All components publish one compact runtime namespace: PREFIX_fnc_* / PREFIX_*.
#undef FUNC
#define FUNC(var1) FUNCMAIN(var1)
#undef GVAR
#define GVAR(var1) GVARMAIN(var1)

#ifdef DISABLE_COMPILE_CACHE
    #define PREP(fncName) FUNC(fncName) = compile preprocessFileLineNumbers QPATHTOF(functions\DOUBLES(fnc,fncName).sqf)
#else
    #define PREP(fncName) [QPATHTOF(functions\DOUBLES(fnc,fncName).sqf), QFUNC(fncName)] call CBA_fnc_compileFunction
#endif

#define COMMAND_POLL_INTERVAL 0.25
#define CAMPAIGN_MONITOR_INTERVAL 12
#define MAX_LOCATION_RESULTS 30
#define MAX_SAVE_RESULTS 20
#define MAX_INTEL_RESULTS 15
#define MAX_ANNOUNCEMENT_LENGTH 300
#define EMBED_COLOR_DEFAULT 5793266
#define EMBED_COLOR_SUCCESS 5763719
#define EMBED_COLOR_ERROR 15548997
