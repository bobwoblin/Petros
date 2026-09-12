#ifndef PROJECT_SCRIPT_MACROS_HPP
#define PROJECT_SCRIPT_MACROS_HPP

#define DOUBLES(var1,var2) var1##_##var2
#define TRIPLES(var1,var2,var3) var1##_##var2##_##var3
#define QUOTE(var1) #var1
#define ARR_2(arg1,arg2) arg1, arg2

#define ADDON DOUBLES(PREFIX,COMPONENT)

#define PATHTO_SYS(var1,var2,var3) \MAINPREFIX\var1\addons\var2\var3.sqf
#define PATHTOF_SYS(var1,var2,var3) \MAINPREFIX\var1\addons\var2\var3
#define PATHTOF(var1) PATHTOF_SYS(PREFIX,COMPONENT,var1)
#define QPATHTOF(var1) QUOTE(PATHTOF(var1))
#define COMPILE_SCRIPT(var1) compileScript ['PATHTO_SYS(PREFIX,COMPONENT,var1)']

#define GVAR(var1) DOUBLES(ADDON,var1)
#define GVARMAIN(var1) DOUBLES(PREFIX,var1)
#define QGVAR(var1) QUOTE(GVAR(var1))

#define FUNC(var1) TRIPLES(ADDON,fnc,var1)
#define FUNCMAIN(var1) TRIPLES(PREFIX,fnc,var1)
#define QFUNC(var1) QUOTE(FUNC(var1))

#define LSTRING(var1) QUOTE(TRIPLES(STR,ADDON,var1))
#define CSTRING(var1) QUOTE(TRIPLES($STR,ADDON,var1))
#define LLSTRING(var1) localize LSTRING(var1)

#define INFO(message) diag_log format ["[%1] %2", "INFO", message]
#define WARNING(message) diag_log format ["[%1] %2", "WARNING", message]
#define ERROR_1(message,arg1) diag_log format ["[%1] %2", "ERROR", format [message,arg1]]

#endif
