# Copy this file to config.local.py and fill in your IDs/token.
# Edit presentation.py for Discord embed styling.
BOT_TOKEN = ""
APPLICATION_ID = ""
# APPLICATION_ID above belongs to the bot, not necessarily the player application.
GUILD_ID = ""

COMMAND_CHANNEL_ID = ""
EVENT_CHANNEL_ID = ""

SERVER_NAME = "Antistasi Server"

# Public player Rich Presence settings. Edit only your server's config.local.py;
# restart Petros/Arma to apply. The server sends these public fields to players.
# Copy the Application ID from your own Discord Developer Portal application.
# Discord displays that application's name; Petros does not override it.
RICH_PRESENCE_ENABLED = True
RICH_PRESENCE_APPLICATION_ID = "YOUR_DISCORD_APPLICATION_ID"
RICH_PRESENCE_UPDATE_INTERVAL = 15  # Seconds, clamped to 15-300.
RICH_PRESENCE_DETAILS = "Antistasi Ultimate"  # Static text alongside the live server name.
# Optional asset keys must match Rich Presence assets in the player application.
# Leave keys empty for no art. Text is used only when its image key is present.
RICH_PRESENCE_LARGE_IMAGE_KEY = ""
RICH_PRESENCE_LARGE_IMAGE_TEXT = ""
RICH_PRESENCE_SMALL_IMAGE_KEY = ""
RICH_PRESENCE_SMALL_IMAGE_TEXT = ""

# Bot display settings. Live map/player/war information is still appended.
BOT_PRESENCE_STATUS = "online"  # online, idle, dnd, invisible
BOT_PRESENCE_ACTIVITY_TYPE = "playing"  # playing, listening, watching, competing
BOT_PRESENCE_TEXT = ""  # Empty uses SERVER_NAME.

# BattlEye RCon is used only for fixed dedicated-server lifecycle commands.
# Match these values to BEServer_x64.cfg. Petros always connects to localhost.
RCON_PORT = 2301
RCON_PASSWORD = ""

ADMIN_USER_IDS = []
ADMIN_ROLE_IDS = []

NOTIFY_SERVER_ONLINE = True
NOTIFY_PLAYER_JOINS = True
NOTIFY_PLAYER_LEAVES = True
NOTIFY_TERRITORY = True
NOTIFY_WAR_LEVEL = True
