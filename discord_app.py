"""
Public Discord application identifiers (Developer Portal → General Information).

The bot token is secret and must live only in `.env` (see `.env.example`).
"""
from __future__ import annotations

# Application ID — used for OAuth invite links and API references.
APPLICATION_ID = "1491310298735312976"

# Public key — only needed if you add an HTTP interactions endpoint later (slash commands over HTTPS).
# The Gateway bot in DiscordBot.py does not read this.
PUBLIC_KEY = "a21194cacc5f70a2c5c3a619f39927724ea015f4670ff94c8520cbd25210bc8e"


def bot_invite_url(
    permissions: int = 84992,
) -> str:
    """
    Default permissions: View Channel, Send Messages, Embed Links, Read Message History.
    Tweak in the Developer Portal URL Generator if you need more.
    """
    return (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={APPLICATION_ID}&permissions={permissions}&scope=bot"
    )
