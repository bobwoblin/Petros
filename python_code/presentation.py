"""Editable Discord presentation for Petros.

This file contains display-only values. Keep credentials and server IDs in
config.local.py.
"""

# Shared embed chrome. {server} is replaced with SERVER_NAME.
EMBED = {
    "author": "",
    "footer": "Antistasi Ultimate • {server}",
    "timestamp": True,
    "server_field": "Server",
}

# Common colors used by Python-side embeds.
COLORS = {
    "default": 0x5865F2,
    "success": 0x57F287,
    "warning": 0xFEE75C,
    "error": 0xED4245,
    "neutral": 0x2B2D31,
}

# Automatic event embeds. Edit titles/colors here without touching bot logic.
EVENTS = {
    "server_online": {
        "title": "🟢 Petros Online",
        "description": "**{server} is online.**",
        "color": COLORS["success"],
    },
    "player_join": {
        "title": "Player Joined",
        "description": "{player} joined the server.",
        "color": COLORS["default"],
    },
    "player_leave": {
        "title": "Player Left",
        "description": "{player} left the server.",
        "color": COLORS["neutral"],
    },
    "territory_gain": {
        "title": "🟢 Territory Gained",
        "description": "Resistance control established.",
        "color": COLORS["success"],
    },
    "territory_loss": {
        "title": "🔴 Territory Lost",
        "description": "Resistance control lost.",
        "color": COLORS["error"],
    },
    "war_increase": {
        "title": "⚔️ War Level Increased",
        "description": "The campaign War Level increased.",
        "color": COLORS["warning"],
    },
}
