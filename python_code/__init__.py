"""Petros: minimal Discord Gateway/REST bridge for Antistasi Ultimate via Pythia."""

from collections import deque
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import queue
import random
import runpy
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

API_BASE = "https://discord.com/api/v10"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
USER_AGENT = "Petros/1.0 (Antistasi Ultimate Discord bridge)"

INFO_COMMANDS = {
    "help", "ping", "status", "players", "campaign", "territory",
    "locations", "war", "resources", "missions",
}
SERVER_COMMANDS = {"servermissions", "loadmission", "restartmission", "missionselect"}
MANAGEMENT_COMMANDS = {"save", "announce", "saves", "loadsave"} | SERVER_COMMANDS
ALL_COMMANDS = INFO_COMMANDS | MANAGEMENT_COMMANDS
LOCATION_CHOICES = (
    ("All", "all"),
    ("Towns", "towns"),
    ("Outposts", "outposts"),
    ("Military Bases", "bases"),
    ("Airports", "airports"),
    ("Resources", "resources"),
    ("Factories", "factories"),
    ("Seaports", "seaports"),
)
LOCATION_VALUES = frozenset(value for _, value in LOCATION_CHOICES)
EVENT_SETTINGS = {
    "server_online": "NOTIFY_SERVER_ONLINE",
    "player_join": "NOTIFY_PLAYER_JOINS",
    "player_leave": "NOTIFY_PLAYER_LEAVES",
    "territory_gain": "NOTIFY_TERRITORY",
    "territory_loss": "NOTIFY_TERRITORY",
    "war_increase": "NOTIFY_WAR_LEVEL",
}

_PRESENTATION_DEFAULTS = {
    "EMBED": {
        "author": "Petros",
        "footer": "Petros • Antistasi Ultimate • {server}",
        "timestamp": True,
        "server_field": "Server",
    },
    "COLORS": {
        "default": 0x5865F2,
        "success": 0x57F287,
        "warning": 0xFEE75C,
        "error": 0xED4245,
        "neutral": 0x2B2D31,
    },
    "EVENTS": {},
}

_DEFAULTS = {
    "BOT_TOKEN": "",
    "APPLICATION_ID": "",
    "GUILD_ID": "",
    "COMMAND_CHANNEL_ID": "",
    "EVENT_CHANNEL_ID": "",
    "SERVER_NAME": "Antistasi Server",
    "RICH_PRESENCE_ENABLED": False,
    "RICH_PRESENCE_APPLICATION_ID": "",
    "RICH_PRESENCE_UPDATE_INTERVAL": 15,
    "RICH_PRESENCE_DETAILS": "Antistasi Ultimate",
    "RICH_PRESENCE_LARGE_IMAGE_KEY": "",
    "RICH_PRESENCE_LARGE_IMAGE_TEXT": "",
    "RICH_PRESENCE_SMALL_IMAGE_KEY": "",
    "RICH_PRESENCE_SMALL_IMAGE_TEXT": "",
    "BOT_PRESENCE_STATUS": "online",
    "BOT_PRESENCE_ACTIVITY_TYPE": 0,
    "BOT_PRESENCE_TEXT": "",
    "RCON_PORT": 2301,
    "RCON_PASSWORD": "",
    "ADMIN_USER_IDS": [],
    "ADMIN_ROLE_IDS": [],
    "NOTIFY_SERVER_ONLINE": True,
    "NOTIFY_PLAYER_JOINS": True,
    "NOTIFY_PLAYER_LEAVES": True,
    "NOTIFY_TERRITORY": True,
    "NOTIFY_WAR_LEVEL": True,
}

_config = dict(_DEFAULTS)
_start_lock = threading.Lock()
_started = False
_rest_ready = False
_commands_ready = False
_gateway_ready = False
_last_sqf_poll = 0.0
_mission_catalog = ()

_incoming = queue.Queue(maxsize=50)
_outgoing = deque()
_out_lock = threading.Lock()
_out_event = threading.Event()
_OUT_MAX = 50

_pending = {}
_pending_lock = threading.Lock()
_recent_ids = deque(maxlen=256)

_gateway_seq = None
_gateway_session_id = None
_gateway_resume_url = None

_presentation = dict(_PRESENTATION_DEFAULTS)

_presence_lock = threading.Lock()
_presence_pipe = None
_presence_application_id = ""
_presence_started_at = 0
_presence_requested = None
_presence_thread = None
_presence_wake = threading.Event()
_presence_last_activity = None
_presence_diagnostics = {}
_bot_campaign = None


def _presence_log(stage, message):
    if _presence_diagnostics.get(stage) != message:
        _log(message)
        _presence_diagnostics[stage] = message


class _PresencePipe:
    """Keep CRT file ownership, but preserve Win32 pipe errors and byte counts."""

    def __init__(self, pipe, handle, kernel32):
        self.pipe = pipe
        self.handle = handle
        self.kernel32 = kernel32

    def read(self, size):
        buffer = ctypes.create_string_buffer(size)
        count = wintypes.DWORD()
        if not self.kernel32.ReadFile(self.handle, buffer, size, ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[:count.value]

    def write(self, data):
        data = bytes(data)
        count = wintypes.DWORD()
        if not self.kernel32.WriteFile(self.handle, data, len(data), ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return count.value

    def close(self):
        self.pipe.close()


def _presence_frame(opcode, payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<II", int(opcode), len(raw)) + raw


def _presence_read_exact(pipe, size, deadline):
    data = bytearray()
    while len(data) < size:
        if time.monotonic() >= deadline:
            raise OSError("Discord IPC response timed out")
        try:
            chunk = pipe.read(size - len(data))
        except OSError as exc:
            if getattr(exc, "winerror", None) != 232:  # PIPE_NOWAIT: no data yet
                raise
            chunk = None
        if chunk is None:
            time.sleep(0.01)
            continue
        if not chunk:
            raise OSError("Discord IPC pipe closed")
        data.extend(chunk)
    return bytes(data)


def _presence_write_all(pipe, data):
    view = memoryview(data)
    offset = 0
    deadline = time.monotonic() + 2.0
    while offset < len(view):
        if time.monotonic() >= deadline:
            raise OSError("Discord IPC write timed out")
        written = pipe.write(view[offset:])
        if not written:
            time.sleep(0.01)
            continue
        offset += written


def _presence_read_frame(pipe, deadline):
    opcode, size = struct.unpack("<II", _presence_read_exact(pipe, 8, deadline))
    if size > 1024 * 1024:
        raise OSError("Discord IPC response is too large")
    payload = _presence_read_exact(pipe, size, deadline)
    return opcode, payload


def _presence_response(pipe, nonce=None, pong=False):
    deadline = time.monotonic() + 2.0
    while True:
        opcode, raw = _presence_read_frame(pipe, deadline)
        if opcode == 3:
            _presence_write_all(pipe, struct.pack("<II", 4, len(raw)) + raw)
            continue
        if pong and opcode == 4 and raw == nonce:
            return
        if opcode == 4:
            continue
        if opcode == 2:
            raise OSError("Discord IPC CLOSE: " + _clip(raw.decode("utf-8", errors="replace"), 256))
        if opcode != 1:
            raise OSError("Discord IPC invalid opcode: " + str(opcode))
        response = json.loads(raw.decode("utf-8"))
        if not isinstance(response, dict):
            raise ValueError("Invalid Discord IPC response")
        if response.get("evt") == "ERROR":
            raise OSError("Discord RPC rejected request: " + _clip(response.get("data"), 256))
        if nonce is None:
            if response.get("cmd") != "DISPATCH" or response.get("evt") != "READY":
                raise OSError("Discord IPC handshake did not return DISPATCH READY")
            return
        if not pong and response.get("nonce") == nonce and response.get("cmd") == "SET_ACTIVITY":
            if response.get("evt") is not None:
                raise ValueError("Invalid Discord SET_ACTIVITY acknowledgement")
            return


def _presence_open_pipe():
    if sys.platform != "win32":
        raise OSError("Discord Rich Presence is supported on Windows clients")
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_state = kernel32.SetNamedPipeHandleState
    set_state.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
                         ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    set_state.restype = wintypes.BOOL
    for operation in (kernel32.ReadFile, kernel32.WriteFile):
        operation.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        operation.restype = wintypes.BOOL
    last_error = None
    for index in range(10):
        path = r"\\?\pipe\discord-ipc-{}".format(index)
        try:
            pipe = open(path, "r+b", buffering=0)
        except OSError as exc:
            if not isinstance(exc, FileNotFoundError):
                last_error = exc
            continue
        handle = msvcrt.get_osfhandle(pipe.fileno())
        mode = wintypes.DWORD(1)  # PIPE_READMODE_BYTE | PIPE_NOWAIT
        if not set_state(handle, ctypes.byref(mode), None, None):
            error = ctypes.WinError(ctypes.get_last_error())
            pipe.close()
            raise OSError("Discord IPC setup failed: " + str(error)) from error
        # Python 3.10 FileIO turns ERROR_NO_DATA into EINVAL without winerror.
        # Native I/O keeps NOWAIT polling and deadlines independent of the CRT.
        _presence_log("pipe", "Discord IPC connected: discord-ipc-" + str(index))
        return _PresencePipe(pipe, handle, kernel32)
    if last_error is not None:
        raise OSError("Discord IPC open failed: " + str(last_error)) from last_error
    raise OSError("Discord IPC pipe not found")


def _presence_close_locked():
    global _presence_pipe, _presence_application_id, _presence_last_activity
    pipe = _presence_pipe
    _presence_pipe = None
    _presence_application_id = ""
    _presence_last_activity = None
    if pipe is not None:
        try:
            pipe.close()
        except OSError:
            pass


def _presence_connect_locked(application_id):
    global _presence_pipe, _presence_application_id
    if _presence_pipe is not None and _presence_application_id == application_id:
        return
    _presence_close_locked()
    pipe = _presence_open_pipe()
    try:
        _presence_write_all(pipe, _presence_frame(0, {"v": 1, "client_id": application_id}))
        _presence_response(pipe)
    except Exception as exc:
        try:
            pipe.close()
        except OSError:
            pass
        if isinstance(exc, (OSError, ValueError)):
            raise OSError("Discord handshake failed: " + str(exc)) from exc
        raise
    _presence_pipe = pipe
    _presence_application_id = application_id
    _presence_log("handshake", "Discord handshake accepted")


def _presence_activity(details, state, current, maximum, large_image, large_text, small_image="", small_text=""):
    global _presence_started_at
    if not _presence_started_at:
        _presence_started_at = int(time.time())
    activity = {
        "type": 0,
        "details": _clip(details, 128) or None,
        "state": _clip(state, 128) or None,
        "timestamps": {"start": _presence_started_at},
        "instance": True,
    }
    if maximum > 0 and current > 0:
        current = max(0, min(int(current), int(maximum)))
        activity["party"] = {"id": "petros", "size": [current, int(maximum)]}
    assets = {}
    if large_image:
        assets["large_image"] = _clip(large_image, 256)
    if large_image and large_text:
        assets["large_text"] = _clip(large_text, 128)
    if small_image:
        assets["small_image"] = _clip(small_image, 256)
        if small_text:
            assets["small_text"] = _clip(small_text, 128)
    if assets:
        activity["assets"] = assets
    return {key: value for key, value in activity.items() if value is not None}


def _presence_send_locked(activity):
    if _presence_pipe is None:
        raise OSError("Discord IPC is not connected")
    payload = {
        "cmd": "SET_ACTIVITY",
        "args": {"pid": os.getpid(), "activity": activity},
        "nonce": str(time.time_ns()),
    }
    try:
        _presence_write_all(_presence_pipe, _presence_frame(1, payload))
        _presence_response(_presence_pipe, payload["nonce"])
    except (OSError, ValueError) as exc:
        raise OSError("Discord activity failed: " + str(exc)) from exc
    _presence_log("activity", "Discord activity cleared" if activity is None else "Discord activity accepted")


def _presence_sync(application_id, activity):
    global _presence_last_activity
    _presence_connect_locked(application_id)
    if activity != _presence_last_activity:
        _presence_send_locked(activity)
        _presence_last_activity = activity
    else:
        ping = _presence_frame(3, {"nonce": str(time.time_ns())})
        try:
            _presence_write_all(_presence_pipe, ping)
            _presence_response(_presence_pipe, ping[8:], pong=True)
        except (OSError, ValueError) as exc:
            raise OSError("Discord IPC disconnected: " + str(exc)) from exc


def _presence_worker():
    next_update = 0.0
    try:
        _presence_log("worker", "Rich Presence worker started")
        while True:
            with _presence_lock:
                requested = _presence_requested
                _presence_wake.clear()
            if requested is None:
                try:
                    if _presence_pipe is not None:
                        _presence_send_locked(None)
                except (OSError, ValueError) as exc:
                    _presence_log("error", "Rich Presence clear failed: " + str(exc))
                finally:
                    _presence_close_locked()
                next_update = 0.0
                _presence_wake.wait()
                continue
            delay = next_update - time.monotonic()
            if delay > 0:
                _presence_wake.wait(delay)
                continue
            try:
                _presence_sync(*requested)
                if _presence_diagnostics.pop("error", None) is not None:
                    _log("Rich Presence recovered; Discord activity accepted")
            except (OSError, ValueError) as exc:
                _presence_close_locked()
                _presence_log("error", str(exc))
            next_update = time.monotonic() + 15.0
    except Exception as exc:
        _presence_log("error", "Rich Presence worker failed: " + type(exc).__name__ + ": " + str(exc))
    finally:
        _presence_close_locked()


def _log(message):
    print("[PETROS/PY] " + str(message), flush=True)


def _load_config():
    global _config, _presentation
    path = os.path.join(os.path.dirname(__file__), "config.local.py")
    if not os.path.isfile(path):
        raise RuntimeError("config.local.py is missing; copy config.example.py and configure Petros")
    loaded = runpy.run_path(path)
    presentation_path = os.path.join(os.path.dirname(__file__), "presentation.py")
    if not os.path.isfile(presentation_path):
        raise RuntimeError("presentation.py is missing")
    display = runpy.run_path(presentation_path)

    cfg = dict(_DEFAULTS)
    for key in cfg:
        if key in loaded:
            cfg[key] = loaded[key]

    for key in ("BOT_TOKEN", "APPLICATION_ID", "GUILD_ID"):
        if not str(cfg[key]).strip():
            raise RuntimeError(key + " is required in config.local.py")
    for key in ("APPLICATION_ID", "GUILD_ID", "COMMAND_CHANNEL_ID", "EVENT_CHANNEL_ID"):
        value = str(cfg[key]).strip()
        if value and not value.isdigit():
            raise RuntimeError(key + " must be a Discord snowflake ID")
        cfg[key] = value
    cfg["BOT_TOKEN"] = str(cfg["BOT_TOKEN"]).strip()
    cfg["SERVER_NAME"] = str(cfg["SERVER_NAME"]).strip() or "Antistasi Server"
    cfg["RICH_PRESENCE_ENABLED"] = cfg["RICH_PRESENCE_ENABLED"] is True
    application_id = str(cfg["RICH_PRESENCE_APPLICATION_ID"]).strip()
    cfg["RICH_PRESENCE_APPLICATION_ID"] = application_id
    if cfg["RICH_PRESENCE_ENABLED"] and not (
        application_id.isascii() and application_id.isdigit() and 17 <= len(application_id) <= 20
    ):
        _log("Player Rich Presence disabled: set RICH_PRESENCE_APPLICATION_ID to a valid Discord Application ID "
             "in server config.local.py, then restart Petros/Arma")
        cfg["RICH_PRESENCE_ENABLED"] = False
    configured_interval = cfg["RICH_PRESENCE_UPDATE_INTERVAL"]
    try:
        interval = int(configured_interval)
        corrected_interval = not 15 <= interval <= 300
        interval = max(15, min(300, interval))
    except (TypeError, ValueError, OverflowError):
        interval, corrected_interval = 15, True
    cfg["RICH_PRESENCE_UPDATE_INTERVAL"] = interval
    if corrected_interval and cfg["RICH_PRESENCE_ENABLED"]:
        _log("RICH_PRESENCE_UPDATE_INTERVAL must be 15-300 seconds; using " + str(interval))
    for key in ("RICH_PRESENCE_DETAILS", "RICH_PRESENCE_LARGE_IMAGE_KEY", "RICH_PRESENCE_LARGE_IMAGE_TEXT",
                "RICH_PRESENCE_SMALL_IMAGE_KEY", "RICH_PRESENCE_SMALL_IMAGE_TEXT", "BOT_PRESENCE_TEXT"):
        cfg[key] = _clip(cfg[key], 256).strip()
    if cfg["BOT_PRESENCE_STATUS"] not in ("online", "idle", "dnd", "invisible"):
        _log("Invalid BOT_PRESENCE_STATUS; using online")
        cfg["BOT_PRESENCE_STATUS"] = "online"
    # Keep the previously documented numeric values compatible.
    activity_type = {"playing": 0, "listening": 2, "watching": 3, "competing": 5,
                     "0": 0, "2": 2, "3": 3, "5": 5}.get(str(cfg["BOT_PRESENCE_ACTIVITY_TYPE"]).strip().lower())
    if activity_type is None:
        _log("Invalid BOT_PRESENCE_ACTIVITY_TYPE; using playing")
        activity_type = 0
    cfg["BOT_PRESENCE_ACTIVITY_TYPE"] = activity_type
    cfg["RCON_PASSWORD"] = str(cfg["RCON_PASSWORD"]).strip()
    try:
        cfg["RCON_PORT"] = int(cfg["RCON_PORT"])
    except (TypeError, ValueError):
        raise RuntimeError("RCON_PORT must be an integer") from None
    if not 1 <= cfg["RCON_PORT"] <= 65535:
        raise RuntimeError("RCON_PORT must be between 1 and 65535")
    for key in ("ADMIN_USER_IDS", "ADMIN_ROLE_IDS"):
        values = {str(value).strip() for value in cfg[key] if str(value).strip()}
        if any(not value.isdigit() for value in values):
            raise RuntimeError(key + " contains a non-snowflake value")
        cfg[key] = values
    for key in (
        "NOTIFY_SERVER_ONLINE", "NOTIFY_PLAYER_JOINS",
        "NOTIFY_PLAYER_LEAVES", "NOTIFY_TERRITORY", "NOTIFY_WAR_LEVEL",
    ):
        cfg[key] = bool(cfg[key])

    cfg["EVENT_CHANNEL_ID"] = cfg["EVENT_CHANNEL_ID"] or cfg["COMMAND_CHANNEL_ID"]

    embed = dict(_PRESENTATION_DEFAULTS["EMBED"])
    embed.update(display.get("EMBED", {}))
    colors = dict(_PRESENTATION_DEFAULTS["COLORS"])
    colors.update(display.get("COLORS", {}))
    events = dict(display.get("EVENTS", {}))

    _config = cfg
    _presentation = {"EMBED": embed, "COLORS": colors, "EVENTS": events}


def _clip(value, limit):
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[:limit - 1] + "…"


def _make_embed(title, description="", fields=None, color=0, include_server=False):
    title = _clip(title, 256)
    description = _clip(description, 4096)
    style = _presentation["EMBED"]
    author = _clip(style.get("author", "Petros"), 256)
    footer = _clip(_format_display(style.get("footer", "")), 2048)
    raw_fields = list(fields or [])
    if include_server:
        raw_fields.insert(0, [style.get("server_field", "Server"), _config["SERVER_NAME"], True])

    fixed = len(title) + len(description) + len(author) + len(footer)
    if fixed > 6000:
        description = _clip(description, max(0, 6000 - len(title) - len(author) - len(footer)))
        fixed = len(title) + len(description) + len(author) + len(footer)

    built = []
    used = fixed
    for item in raw_fields[:25]:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        name = _clip(item[0], 256) or "Value"
        value = _clip(item[1], 1024) or "—"
        inline = bool(item[2]) if len(item) > 2 else False
        remaining = 6000 - used - len(name)
        if remaining <= 0:
            break
        value = _clip(value, min(1024, remaining))
        if not value:
            break
        built.append({"name": name, "value": value, "inline": inline})
        used += len(name) + len(value)

    embed = {
        "author": {"name": author},
        "title": title,
        "description": description,
        "fields": built,
        "footer": {"text": footer},
    }
    if style.get("timestamp", True):
        embed["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if color:
        embed["color"] = int(color)
    return embed


def _message_payload(title, description="", fields=None, color=0, include_server=False):
    return {
        "embeds": [_make_embed(title, description, fields, color, include_server)],
        "allowed_mentions": {"parse": []},
    }


def _format_display(template, **values):
    values.setdefault("server", _config["SERVER_NAME"])
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def _rest_request(method, path, payload=None, auth=True, timeout=8.0, max_retries=3):
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"User-Agent": USER_AGENT}
    if auth:
        headers["Authorization"] = "Bot " + _config["BOT_TOKEN"]
    if body is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(API_BASE + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
                if not data:
                    return None
                return json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            if exc.code == 429 and attempt < max_retries:
                retry_after = exc.headers.get("Retry-After")
                try:
                    parsed = json.loads(response_body.decode("utf-8")) if response_body else {}
                    retry_after = parsed.get("retry_after", retry_after)
                except (ValueError, UnicodeDecodeError):
                    pass
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = 1.0
                _log("Discord HTTP 429; respecting Retry-After")
                time.sleep(max(0.05, min(delay, 30.0)))
                continue
            if exc.code in (500, 502, 503, 504) and attempt < max_retries:
                time.sleep((1.0, 2.0, 5.0)[min(attempt, 2)])
                continue
            raise RuntimeError("Discord HTTP " + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            if attempt < max_retries:
                time.sleep((1.0, 2.0, 5.0)[min(attempt, 2)])
                continue
            raise RuntimeError("Discord network request failed: " + type(exc).__name__) from None


def _commands_payload():
    location_choices = [{"name": name, "value": value} for name, value in LOCATION_CHOICES]
    descriptions = {
        "help": "Show the Petros command summary.",
        "ping": "Show Petros and server health.",
        "status": "Show current Antistasi server status.",
        "players": "List human players currently online.",
        "campaign": "Show a compact Antistasi campaign overview.",
        "territory": "Show current strategic territory ownership.",
        "locations": "List player-controlled strategic locations.",
        "war": "Show the current War Level.",
        "resources": "Show current resistance resources.",
        "missions": "Show currently active Antistasi mission types.",
        "servermissions": "List Arma multiplayer missions available to the server. Admin only.",
        "loadmission": "Load an Arma multiplayer mission by template name. Admin only.",
        "restartmission": "Restart the currently loaded Arma mission. Admin only.",
        "missionselect": "End the current mission and return to mission selection. Admin only.",
        "saves": "List Antistasi campaign saves available for the current map. Admin only.",
        "loadsave": "Load an Antistasi campaign save by ID during setup. Admin only.",
        "save": "Request an Antistasi campaign save. Admin only.",
        "announce": "Broadcast a plain-text in-game announcement. Admin only.",
    }
    commands = []
    for name, description in descriptions.items():
        command = {"name": name, "description": description, "type": 1}
        if name == "locations":
            command["options"] = [{
                "name": "type",
                "description": "Location category",
                "type": 3,
                "required": False,
                "choices": location_choices,
            }]
        elif name == "announce":
            command["options"] = [{
                "name": "message",
                "description": "Plain-text announcement (max 300 characters)",
                "type": 3,
                "required": True,
                "min_length": 1,
                "max_length": 300,
            }]
        elif name == "loadmission":
            command["options"] = [{
                "name": "mission",
                "description": "Exact mission template from /servermissions",
                "type": 3,
                "required": True,
                "min_length": 1,
                "max_length": 160,
            }]
        elif name == "loadsave":
            command["options"] = [{
                "name": "id",
                "description": "Campaign ID shown by /saves",
                "type": 3,
                "required": True,
                "min_length": 1,
                "max_length": 64,
            }]
        commands.append(command)
    return commands

def _is_admin(user_id, roles, cfg=None):
    cfg = cfg or _config
    return user_id in cfg["ADMIN_USER_IDS"] or bool(set(roles) & cfg["ADMIN_ROLE_IDS"])


def _string_option(options, name, missing, invalid):
    if len(options) != 1:
        return None, missing
    option = options[0]
    value = option.get("value")
    if option.get("name") != name or option.get("type") != 3 or not isinstance(value, str):
        return None, invalid
    return value.strip(), ""


def _validate_options(command, raw_options):
    options = raw_options or []
    if not isinstance(options, list):
        return False, "Invalid command options.", []
    if command == "locations":
        if not options:
            return True, "", ["all"]
        value, error = _string_option(
            options,
            "type",
            "Invalid location option.",
            "Invalid location option type.",
        )
        if error:
            return False, error, []
        value = value.lower()
        if value not in LOCATION_VALUES:
            return False, "Unsupported location type.", []
        return True, "", [value]
    if command == "announce":
        value, error = _string_option(
            options,
            "message",
            "A message is required.",
            "Invalid announcement option type.",
        )
        if error:
            return False, error, []
        if not value:
            return False, "Announcement can't be blank.", []
        if len(value) > 300:
            return False, "Announcement must be 300 characters or fewer.", []
        if (
            any(ord(char) < 32 or ord(char) == 127 for char in value)
            or "<" in value
            or ">" in value
        ):
            return (
                False,
                "Announcement must be plain text without control characters or angle brackets.",
                [],
            )
        return True, "", [value]
    if command in ("loadmission", "loadsave"):
        name, limit, allowed, missing, invalid, unsupported = {
            "loadmission": (
                "mission",
                160,
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.- ",
                "A mission template is required.",
                "Invalid mission option type.",
                "Mission template contains unsupported characters.",
            ),
            "loadsave": (
                "id",
                64,
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-",
                "A campaign ID is required.",
                "Invalid save ID option type.",
                "Campaign ID contains unsupported characters.",
            ),
        }[command]
        value, error = _string_option(options, name, missing, invalid)
        if error:
            return False, error, []
        if not value or len(value) > limit or any(char not in allowed for char in value):
            return False, unsupported, []
        return True, "", [value]
    if options:
        return False, "This command doesn't accept options.", []
    return True, "", []


def _validate_interaction(interaction, cfg=None):
    cfg = cfg or _config
    if not isinstance(interaction, dict) or interaction.get("type") != 2:
        return False, "interaction_type", None
    if str(interaction.get("guild_id", "")) != cfg["GUILD_ID"]:
        return False, "wrong_guild", None
    data = interaction.get("data") or {}
    command = data.get("name")
    if command not in ALL_COMMANDS:
        return False, "unknown_command", None
    if (
        cfg["COMMAND_CHANNEL_ID"]
        and str(interaction.get("channel_id", "")) != cfg["COMMAND_CHANNEL_ID"]
    ):
        return False, "wrong_channel", None

    interaction_id = str(interaction.get("id", ""))
    token = str(interaction.get("token", ""))
    if not interaction_id:
        return False, "missing_id", None
    if not token:
        return False, "missing_token", None

    member = interaction.get("member") or {}
    user = member.get("user") or interaction.get("user") or {}
    user_id = str(user.get("id", ""))
    roles = [str(role) for role in member.get("roles", [])]
    if not user_id:
        return False, "missing_user", None

    if command in MANAGEMENT_COMMANDS and not _is_admin(user_id, roles, cfg):
        return False, "unauthorized_management", None

    valid, error, values = _validate_options(command, data.get("options"))
    if not valid:
        return False, "options:" + error, None
    return True, "", {
        "id": interaction_id,
        "token": token,
        "command": command,
        "options": values,
        "ephemeral": command in MANAGEMENT_COMMANDS,
    }


def _remember_interaction(interaction_id):
    if interaction_id in _recent_ids:
        return False
    _recent_ids.append(interaction_id)
    return True


def _rcon_packet(payload):
    checksum = zlib.crc32(payload) & 0xFFFFFFFF
    return b"BE" + struct.pack("<I", checksum) + payload


def _rcon_parse(packet):
    if len(packet) < 8 or packet[:2] != b"BE":
        raise RuntimeError("BattlEye RCon returned an invalid packet")
    expected = struct.unpack("<I", packet[2:6])[0]
    payload = packet[6:]
    if (zlib.crc32(payload) & 0xFFFFFFFF) != expected or payload[:1] != b"\xff":
        raise RuntimeError("BattlEye RCon packet integrity check failed")
    return payload[1], payload[2:]


def _rcon_command(command, capture_command_messages=False):
    password = _config.get("RCON_PASSWORD", "")
    if not password:
        raise RuntimeError("BattlEye RCon isn't configured in config.local.py")
    try:
        password_bytes = password.encode("ascii")
        command_bytes = command.encode("ascii")
    except UnicodeEncodeError:
        raise RuntimeError("BattlEye RCon values must be ASCII") from None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    try:
        sock.connect(("127.0.0.1", _config["RCON_PORT"]))
        sock.send(_rcon_packet(b"\xff\x00" + password_bytes))
        packet_type, payload = _rcon_parse(sock.recv(65535))
        if packet_type != 0 or payload[:1] != b"\x01":
            raise RuntimeError("BattlEye RCon login failed")

        sequence = 0
        sock.send(_rcon_packet(b"\xff\x01" + bytes((sequence,)) + command_bytes))
        fragments = {}
        command_messages = []
        direct_response = ""
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            try:
                packet_type, payload = _rcon_parse(sock.recv(65535))
            except socket.timeout:
                break
            if packet_type == 2:
                if payload:
                    sock.send(_rcon_packet(b"\xff\x02" + payload[:1]))
                    if capture_command_messages and len(payload) > 1:
                        message = payload[1:].decode("utf-8", "replace").strip()
                        if message:
                            command_messages.append(message)
                continue
            if packet_type != 1 or not payload or payload[0] != sequence:
                continue
            body = payload[1:]
            if len(body) >= 3 and body[0] == 0:
                count = body[1] or 256
                fragments[body[2]] = body[3:]
                if len(fragments) == count:
                    direct_response = (
                        b"".join(fragments[index] for index in range(count))
                        .decode("utf-8", "replace")
                        .strip()
                    )
                    if not capture_command_messages:
                        return direct_response
                    fragments.clear()
                continue
            direct_response = body.decode("utf-8", "replace").strip()
            if not capture_command_messages:
                return direct_response

        if fragments:
            raise RuntimeError("BattlEye RCon response was incomplete")
        if command_messages:
            return "\n".join(command_messages)
        return direct_response
    except (socket.timeout, OSError) as exc:
        raise RuntimeError("BattlEye RCon unavailable: " + type(exc).__name__) from None
    finally:
        sock.close()


def _mission_templates(output):
    templates = []
    for raw in output.splitlines():
        value = raw.strip()
        for prefix in ("(Command) SERVER:", "SERVER:"):
            if value.startswith(prefix):
                value = value[len(prefix):].strip()
                break
        lower = value.lower()
        if not value or lower == "missions on server:":
            continue
        if lower.startswith(("player #", "rcon admin #", "battleye server:")):
            continue
        if value.endswith(("\\", "/")):
            continue
        if value.lower().endswith(".pbo"):
            value = value[:-4]
        if "." in value:
            templates.append(value)
    return templates


def _available_missions():
    missions = []
    errors = []
    for command, capture in (("#mpmissions", True), ("missions", False)):
        try:
            missions.extend(
                _mission_templates(
                    _rcon_command(command, capture_command_messages=capture)
                )
            )
        except RuntimeError as exc:
            errors.append(exc)

    # Arma addon CfgMissions entries aren't guaranteed to appear in the
    # file-oriented BattlEye listings. SQF provides the live Antistasi list.
    missions.extend(_mission_catalog)
    missions = list(dict.fromkeys(missions))
    if not missions and errors:
        raise errors[0]
    return missions


def _run_server_command(command, options):
    if command == "servermissions":
        missions = _available_missions()
        description = (
            "Available mission templates:\n"
            + "\n".join("`{}`".format(item) for item in missions)
            if missions
            else "No mission templates were discovered."
        )
        return _message_payload("Server Missions", description, color=_presentation["COLORS"]["default"], include_server=True)
    if command == "loadmission":
        mission = options[0]
        output = _rcon_command("#mission " + mission)
        description = "Mission load requested: **{}**".format(mission)
        if output:
            description += "\n\n" + _clip(output, 3000)
        return _message_payload("Mission Load", description, color=_presentation["COLORS"]["success"], include_server=True)
    fixed = {
        "restartmission": ("#restart", "Mission Restart", "Current mission restart requested."),
        "missionselect": ("#missions", "Mission Selection", "Mission selection requested."),
    }.get(command)
    if fixed:
        rcon_command, title, description = fixed
        output = _rcon_command(rcon_command)
        if output:
            description += "\n\n" + _clip(output, 3000)
        return _message_payload(title, description, color=_presentation["COLORS"]["warning"], include_server=True)
    raise RuntimeError("Unsupported fixed server command")


def _sqf_bridge_ready():
    return bool(_last_sqf_poll and time.monotonic() - _last_sqf_poll < 3.0)


def _callback(interaction_id, token, payload):
    path = "/interactions/{}/{}/callback".format(interaction_id, urllib.parse.quote(token, safe=""))
    _rest_request("POST", path, payload, auth=False, timeout=2.5, max_retries=0)


def _respond(interaction, content, ephemeral=False):
    interaction_id = str(interaction.get("id", ""))
    token = str(interaction.get("token", ""))
    if not interaction_id or not token:
        return
    data = {"content": _clip(content, 2000), "allowed_mentions": {"parse": []}}
    if ephemeral:
        data["flags"] = 64
    try:
        _callback(interaction_id, token, {"type": 4, "data": data})
    except RuntimeError:
        _log("Interaction response failed")


def _handle_interaction(interaction):
    ok, reason, parsed = _validate_interaction(interaction)
    if not ok:
        if reason in ("wrong_guild", "interaction_type"):
            return
        if reason == "wrong_channel":
            _respond(
                interaction,
                "Petros commands can only be used in the configured server-ops channel.",
                True,
            )
        elif reason == "unknown_command":
            _respond(interaction, "Unknown Petros command.", True)
        elif reason == "unauthorized_management":
            _respond(
                interaction,
                "You aren't authorized to use Petros management commands.",
                True,
            )
        elif reason.startswith("options:"):
            _respond(interaction, reason.split(":", 1)[1], True)
        return

    if not _remember_interaction(parsed["id"]):
        return

    command = parsed["command"]
    if command == "help":
        content = (
            "**Petros**\nAntistasi Ultimate server operations.\n\n"
            "Information: `/ping` `/status` `/players` `/campaign` `/territory` "
            "`/locations` `/war` `/resources` `/missions`\n"
            "Server: `/servermissions` `/loadmission` `/restartmission` `/missionselect`\n"
            "Campaign: `/saves` `/loadsave` `/save` `/announce`"
        )
        _respond(parsed, content)
        return

    if command == "ping":
        state = health()
        content = (
            "Petros online • Gateway {} • REST {} • Commands {} • "
            "Mission bridge {} • RCon {}"
        ).format(
            "ready" if state[1] else "offline",
            "ready" if state[2] else "offline",
            "registered" if state[3] else "pending",
            "ready" if _sqf_bridge_ready() else "inactive",
            "configured" if _config.get("RCON_PASSWORD") else "not configured",
        )
        _respond(parsed, content)
        return

    if command not in SERVER_COMMANDS and not _sqf_bridge_ready():
        _respond(
            interaction,
            "No Arma mission command bridge is active. "
            "Use /servermissions and /loadmission first.",
            True,
        )
        return

    if command in SERVER_COMMANDS:
        with _out_lock:
            queue_full = len(_outgoing) >= _OUT_MAX and not any(
                item.get("kind") == "event" for item in _outgoing
            )
        if queue_full:
            _respond(interaction, "Petros management queue is full. Try again shortly.", True)
            return
    elif _incoming.full():
        _respond(interaction, "Petros command queue is full. Try again shortly.", True)
        return

    defer_data = {"flags": 64} if parsed["ephemeral"] else {}
    try:
        _callback(parsed["id"], parsed["token"], {"type": 5, "data": defer_data})
    except RuntimeError:
        _log("Interaction defer failed")
        return

    with _pending_lock:
        _pending[parsed["id"]] = {"token": parsed["token"], "created": time.monotonic()}

    if command in SERVER_COMMANDS:
        if not _enqueue_out({
            "kind": "rcon",
            "interaction_id": parsed["id"],
            "command": command,
            "options": parsed["options"],
        }, high=True):
            with _pending_lock:
                _pending.pop(parsed["id"], None)
            _log("Petros management queue filled after interaction defer")
        return

    _incoming.put_nowait([parsed["id"], command, parsed["options"]])

def _enqueue_out(item, high=False):
    with _out_lock:
        if len(_outgoing) >= _OUT_MAX:
            if not high:
                return False
            drop_index = None
            for index in range(len(_outgoing) - 1, -1, -1):
                if _outgoing[index].get("kind") == "event":
                    drop_index = index
                    break
            if drop_index is None:
                return False
            del _outgoing[drop_index]
        if high:
            _outgoing.appendleft(item)
        else:
            _outgoing.append(item)
        _out_event.set()
        return True


def _rest_worker():
    global _rest_ready, _commands_ready
    backoffs = (1.0, 2.0, 5.0, 10.0, 30.0)
    failures = 0
    while not _commands_ready:
        try:
            me = _rest_request("GET", "/users/@me")
            if not isinstance(me, dict) or not me.get("id"):
                raise RuntimeError("Discord authentication returned no bot identity")
            _rest_ready = True
            _log("Discord REST authenticated")
            path = "/applications/{}/guilds/{}/commands".format(
                _config["APPLICATION_ID"], _config["GUILD_ID"]
            )
            _rest_request("PUT", path, _commands_payload())
            _commands_ready = True
            _log("Slash commands registered")
        except RuntimeError as exc:
            _log(str(exc))
            if str(exc).startswith("Discord HTTP 4") and not str(exc).startswith(
                "Discord HTTP 429"
            ):
                return
            time.sleep(backoffs[min(failures, len(backoffs) - 1)])
            failures += 1

    while True:
        cutoff = time.monotonic() - 840.0
        with _pending_lock:
            for key in [key for key, value in _pending.items() if value["created"] < cutoff]:
                del _pending[key]
        with _out_lock:
            item = _outgoing.popleft() if _outgoing else None
            if not _outgoing:
                _out_event.clear()
        if item is None:
            _out_event.wait(1.0)
            continue
        try:
            if item["kind"] == "rcon":
                interaction_id = item["interaction_id"]
                try:
                    payload = _run_server_command(item["command"], item["options"])
                except RuntimeError as exc:
                    payload = _message_payload(
                        "Server Command Failed", str(exc), color=_presentation["COLORS"]["error"], include_server=True
                    )
                item = {"kind": "interaction", "interaction_id": interaction_id, "payload": payload}

            if item["kind"] == "interaction":
                interaction_id = item["interaction_id"]
                with _pending_lock:
                    pending = _pending.get(interaction_id)
                if not pending:
                    continue
                path = "/webhooks/{}/{}/messages/@original".format(
                    _config["APPLICATION_ID"], urllib.parse.quote(pending["token"], safe="")
                )
                _rest_request("PATCH", path, item["payload"], auth=False)
                with _pending_lock:
                    _pending.pop(interaction_id, None)
            elif item["kind"] == "event":
                channel_id = _config["EVENT_CHANNEL_ID"]
                if channel_id:
                    _rest_request(
                        "POST",
                        "/channels/{}/messages".format(channel_id),
                        item["payload"],
                    )
        except RuntimeError as exc:
            _log(str(exc))
            if item["kind"] == "interaction":
                with _pending_lock:
                    _pending.pop(item["interaction_id"], None)


def _ws_accept(key):
    digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _mask_payload(payload, mask):
    return bytes(value ^ mask[index & 3] for index, value in enumerate(payload))


def _ws_frame(opcode, payload=b"", mask_key=None):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        header = bytes((first, 0x80 | length))
    elif length <= 0xFFFF:
        header = bytes((first, 0x80 | 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, 0x80 | 127)) + struct.pack("!Q", length)
    key = mask_key or os.urandom(4)
    return header + key + _mask_payload(payload, key)


def _recv_exact(sock, size, buffer):
    while len(buffer) < size:
        chunk = sock.recv(max(4096, size - len(buffer)))
        if not chunk:
            raise _WsClosed(None, "connection lost")
        buffer.extend(chunk)
    data = bytes(buffer[:size])
    del buffer[:size]
    return data


class _WsClosed(Exception):
    def __init__(self, code=None, reason=""):
        super().__init__(reason)
        self.code = code


def _ws_recv_message(sock, buffer):
    fragments = []
    message_opcode = None
    while True:
        head = _recv_exact(sock, 2, buffer)
        first, second = head
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        if first & 0x70:
            raise _WsClosed(1002, "unexpected websocket extension bits")
        if masked:
            raise _WsClosed(1002, "masked server frame")
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", _recv_exact(sock, 2, buffer))[0]
        elif length == 127:
            raw = _recv_exact(sock, 8, buffer)
            length = struct.unpack("!Q", raw)[0]
            if length & (1 << 63):
                raise _WsClosed(1002, "invalid payload length")
        payload = _recv_exact(sock, length, buffer)

        if opcode >= 0x8:
            if not fin or length > 125:
                raise _WsClosed(1002, "invalid control frame")
            if opcode == 0x9:
                sock.sendall(_ws_frame(0xA, payload))
                continue
            if opcode == 0x8:
                try:
                    sock.sendall(_ws_frame(0x8, payload))
                except OSError:
                    pass
                close_code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
                reason = payload[2:].decode("utf-8", "replace") if len(payload) > 2 else ""
                raise _WsClosed(close_code, reason)
            if opcode == 0xA:
                continue
            raise _WsClosed(1002, "reserved control opcode")

        if opcode == 0x1:
            if message_opcode is not None:
                raise _WsClosed(1002, "new data frame during fragmentation")
            message_opcode = opcode
            fragments = [payload]
        elif opcode == 0x0:
            if message_opcode is None:
                raise _WsClosed(1002, "unexpected continuation")
            fragments.append(payload)
        elif opcode == 0x2:
            raise _WsClosed(1003, "binary gateway frame unsupported without compression")
        else:
            raise _WsClosed(1002, "unsupported websocket opcode")

        if fin:
            data = b"".join(fragments)
            return data.decode("utf-8")


def _ws_send_json(sock, payload):
    sock.sendall(_ws_frame(0x1, json.dumps(payload, separators=(",", ":")).encode("utf-8")))


def _gateway_url(url):
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key not in ("v", "encoding", "compress")]
    query.extend((("v", "10"), ("encoding", "json")))
    return urllib.parse.urlunsplit(
        ("wss", parsed.netloc, parsed.path or "/", urllib.parse.urlencode(query), "")
    )


def _ws_connect(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "wss" or not parsed.hostname:
        raise RuntimeError("Discord returned an invalid Gateway URL")
    port = parsed.port or 443
    raw = socket.create_connection((parsed.hostname, port), timeout=10.0)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    host = parsed.hostname if port == 443 else "{}:{}".format(parsed.hostname, port)
    request = (
        "GET {} HTTP/1.1\r\n"
        "Host: {}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: {}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "User-Agent: {}\r\n\r\n"
    ).format(path, host, key, USER_AGENT).encode("ascii")
    sock.sendall(request)
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise RuntimeError("Discord Gateway handshake closed early")
        data.extend(chunk)
        if len(data) > 65536:
            sock.close()
            raise RuntimeError("Discord Gateway handshake was too large")
    header_bytes, leftover = bytes(data).split(b"\r\n\r\n", 1)
    lines = header_bytes.decode("iso-8859-1").split("\r\n")
    if " 101 " not in (lines[0] + " "):
        sock.close()
        raise RuntimeError("Discord Gateway WebSocket upgrade failed")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    if headers.get("sec-websocket-accept") != _ws_accept(key):
        sock.close()
        raise RuntimeError("Discord Gateway WebSocket accept verification failed")
    return sock, bytearray(leftover)


def _gateway_worker():
    global _gateway_seq, _gateway_session_id, _gateway_resume_url
    global _gateway_ready
    backoffs = (1.0, 2.0, 5.0, 10.0, 30.0)
    failures = 0
    gateway_base = None

    while True:
        if not _commands_ready:
            time.sleep(0.5)
            continue
        try:
            if gateway_base is None:
                info = _rest_request("GET", "/gateway/bot")
                gateway_base = info["url"]
            target = _gateway_resume_url or gateway_base
            sock, buffer = _ws_connect(_gateway_url(target))
            hello = json.loads(_ws_recv_message(sock, buffer))
            if hello.get("op") != 10:
                raise RuntimeError("Discord Gateway didn't send HELLO first")
            interval = float(hello["d"]["heartbeat_interval"]) / 1000.0
            can_resume = bool(_gateway_session_id and _gateway_seq is not None)
            if can_resume:
                _ws_send_json(sock, {
                    "op": 6,
                    "d": {
                        "token": _config["BOT_TOKEN"],
                        "session_id": _gateway_session_id,
                        "seq": _gateway_seq,
                    },
                })
            else:
                _ws_send_json(sock, {
                    "op": 2,
                    "d": {
                        "token": _config["BOT_TOKEN"],
                        "intents": 0,
                        "properties": {
                            "os": os.name,
                            "browser": "Petros",
                            "device": "Petros",
                        },
                    },
                })
            next_heartbeat = time.monotonic() + random.random() * interval
            awaiting_ack = False
            failures = 0
            last_presence = None
            next_presence = 0.0

            while True:
                now = time.monotonic()
                if now >= next_heartbeat:
                    if awaiting_ack:
                        raise RuntimeError("Discord Gateway heartbeat ACK timed out")
                    _ws_send_json(sock, {"op": 1, "d": _gateway_seq})
                    awaiting_ack = True
                    next_heartbeat = now + interval

                if _gateway_ready and now >= next_presence:
                    presence = _bot_presence()
                    if presence != last_presence:
                        try:
                            _ws_send_json(sock, {"op": 3, "d": presence})
                        except OSError:
                            _log("Bot presence send failed; reconnecting Gateway")
                            raise
                        last_presence = presence
                        next_presence = now + 15.0

                sock.settimeout(max(0.05, min(1.0, next_heartbeat - time.monotonic())))
                try:
                    message = _ws_recv_message(sock, buffer)
                except socket.timeout:
                    continue
                event = json.loads(message)
                opcode = event.get("op")
                if event.get("s") is not None:
                    _gateway_seq = event["s"]

                if opcode == 0:
                    event_type = event.get("t")
                    data = event.get("d") or {}
                    if event_type == "READY":
                        _gateway_session_id = data.get("session_id")
                        _gateway_resume_url = data.get("resume_gateway_url")
                        _gateway_ready = True
                        last_presence = None
                        next_presence = 0.0
                        _log("Gateway connected")
                    elif event_type == "RESUMED":
                        _gateway_ready = True
                        last_presence = None
                        next_presence = 0.0
                        _log("Gateway resumed")
                    elif event_type == "INTERACTION_CREATE":
                        _handle_interaction(data)
                elif opcode == 1:
                    _ws_send_json(sock, {"op": 1, "d": _gateway_seq})
                elif opcode == 7:
                    raise _WsClosed(None, "Discord requested reconnect")
                elif opcode == 9:
                    resumable = bool(event.get("d"))
                    if not resumable:
                        _gateway_session_id = None
                        _gateway_resume_url = None
                        _gateway_seq = None
                    time.sleep(random.uniform(1.0, 5.0))
                    raise _WsClosed(None, "Discord invalidated session")
                elif opcode == 10:
                    interval = float(event["d"]["heartbeat_interval"]) / 1000.0
                elif opcode == 11:
                    awaiting_ack = False
        except _WsClosed as exc:
            _gateway_ready = False
            if exc.code in (4004, 4010, 4011, 4012, 4013, 4014):
                _log("Discord Gateway closed with non-recoverable code " + str(exc.code))
                return
            if exc.code in (4007, 4009):
                _gateway_session_id = None
                _gateway_resume_url = None
                _gateway_seq = None
            _log("Gateway disconnected")
        except (RuntimeError, ValueError, KeyError, OSError, ssl.SSLError) as exc:
            _gateway_ready = False
            _log("Gateway reconnecting: " + str(exc))
        finally:
            try:
                sock.close()
            except (UnboundLocalError, OSError):
                pass

        delay = backoffs[min(failures, len(backoffs) - 1)] + random.random()
        failures += 1
        time.sleep(delay)


def start():
    """Start Petros once. Network work stays on background threads."""
    global _started
    with _start_lock:
        if _started:
            return health()
        try:
            _load_config()
        except RuntimeError as exc:
            _log(exc)
            return health()
        _started = True
        threading.Thread(target=_rest_worker, name="Petros REST", daemon=True).start()
        threading.Thread(target=_gateway_worker, name="Petros Gateway", daemon=True).start()
        _log("Started")
        return health()


def set_missions(missions):
    """Cache Antistasi CfgMissions identifiers discovered by SQF."""
    global _mission_catalog
    clean = []
    if isinstance(missions, (list, tuple)):
        for item in missions:
            value = str(item).strip()
            if value and "." in value and value not in clean:
                clean.append(value)
    _mission_catalog = tuple(clean)
    return len(_mission_catalog)


def drain_commands(max_items=10):
    """Return queued Discord commands to SQF without blocking."""
    global _last_sqf_poll
    _last_sqf_poll = time.monotonic()
    try:
        limit = max(1, min(int(max_items), 20))
    except (TypeError, ValueError):
        limit = 10
    items = []
    for _ in range(limit):
        try:
            items.append(_incoming.get_nowait())
        except queue.Empty:
            break
    return items


def complete_interaction(
    interaction_id, title, description="", fields=None, color=0, include_server=False
):
    """Queue an edit of one already-deferred interaction response."""
    interaction_id = str(interaction_id)
    with _pending_lock:
        if interaction_id not in _pending:
            return False
    payload = _message_payload(title, description, fields, color, bool(include_server))
    return _enqueue_out(
        {"kind": "interaction", "interaction_id": interaction_id, "payload": payload},
        high=True,
    )


def send_event(kind, description="", fields=None):
    """Queue one automatic Discord event. Returns immediately to SQF."""
    setting = EVENT_SETTINGS.get(kind)
    if setting is None:
        return False
    if setting and not _config.get(setting, False):
        return True
    if not _config.get("EVENT_CHANNEL_ID"):
        return False

    display = _presentation["EVENTS"].get(kind, {})
    title = display.get("title", kind.replace("_", " ").title())
    color = display.get("color", _presentation["COLORS"]["default"])
    values = {"description": description}
    for item in fields or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        key = "_".join(str(item[0]).lower().split())
        values[key] = item[1]
    template = display.get("description", "{description}")
    description = _format_display(template, **values)
    payload = _message_payload(title, description, fields, color, kind == "server_online")
    return _enqueue_out({"kind": "event", "payload": payload}, high=False)



def update_presence(
    application_id,
    details="",
    state="",
    current_players=0,
    max_players=0,
    large_image="",
    large_text="",
    small_image="",
    small_text="",
):
    """Queue local Rich Presence; True means accepted, not acknowledged by Discord."""
    application_id = str(application_id).strip()
    if not application_id.isascii() or not application_id.isdigit() or not 17 <= len(application_id) <= 20:
        return False
    try:
        current_players = int(current_players)
        max_players = int(max_players)
    except (TypeError, ValueError, OverflowError):
        return False
    if current_players < 0 or max_players < 0:
        return False
    global _presence_requested, _presence_thread
    with _presence_lock:
        activity = _presence_activity(
            details, state, current_players, max_players,
            str(large_image).strip(), str(large_text).strip(),
            str(small_image).strip(), str(small_text).strip(),
        )
        _presence_requested = (application_id, activity)
        _presence_wake.set()
        if _presence_thread is None or not _presence_thread.is_alive():
            _presence_thread = threading.Thread(target=_presence_worker, name="Petros IPC", daemon=True)
            _presence_thread.start()
    return True


def clear_presence():
    """Queue a clear without waiting for Discord; the worker owns the pipe."""
    global _presence_started_at, _presence_requested
    with _presence_lock:
        _presence_requested = None
        _presence_started_at = 0
        _presence_wake.set()
    return True


def set_bot_presence(map_name="", players=0, war=-1):
    """Receive the existing campaign monitor's display values via Pythia."""
    global _bot_campaign
    if not isinstance(map_name, str):
        return False
    try:
        players, war = int(players), int(war)
    except (TypeError, ValueError, OverflowError):
        return False
    if players < 0 or war < -1:
        return False
    _bot_campaign = (_clip(map_name, 64), players, war) if map_name else None
    return True


def get_presence_config():
    """Export only public player settings to SQF; never expose bot/RCon credentials."""
    if not _config["RICH_PRESENCE_ENABLED"]:
        return []
    return [
        _config["RICH_PRESENCE_APPLICATION_ID"], _config["RICH_PRESENCE_UPDATE_INTERVAL"],
        _config["RICH_PRESENCE_DETAILS"],
        _config["RICH_PRESENCE_LARGE_IMAGE_KEY"], _config["RICH_PRESENCE_LARGE_IMAGE_TEXT"],
        _config["RICH_PRESENCE_SMALL_IMAGE_KEY"], _config["RICH_PRESENCE_SMALL_IMAGE_TEXT"],
    ]


def _bot_presence():
    name = _clip(_config["BOT_PRESENCE_TEXT"] or _config["SERVER_NAME"], 64)
    campaign = _bot_campaign
    if campaign and time.monotonic() - _last_sqf_poll < 5.0:
        map_name, players, war = campaign
        name += " • {} • {} players".format(map_name, players)
        if war >= 0:
            name += " • War {}".format(war)
    return {"since": None,
            "activities": [{"name": _clip(name, 128), "type": _config["BOT_PRESENCE_ACTIVITY_TYPE"]}],
            "status": _config["BOT_PRESENCE_STATUS"], "afk": False}


def health():
    """Return the minimal runtime state used by Pythia and /ping."""
    return [bool(_started), bool(_gateway_ready), bool(_rest_ready), bool(_commands_ready)]
