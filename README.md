# Anime Notification Discord Bot

Discord bot that can remind a channel when tracked anime airs, with metadata from **[Jikan](https://jikan.moe/)** (unofficial MyAnimeList API).

## One-time Discord setup

Your **Application ID** and **public key** are stored in `discord_app.py` (they are public). The **bot token** is secret — it goes only in `.env`.

1. **[Developer Portal](https://discord.com/developers/applications)** → open your application.
2. **Bot** → create the bot user if needed → under **Privileged Gateway Intents**, turn **Message Content Intent** **ON** → **Save Changes**. (Required or you’ll get `PrivilegedIntentsRequired` when starting the bot.)
3. **Bot** → **Reset / Copy** the token (you will paste it into `.env` as `TOKEN`).
4. In Discord: **User Settings → Advanced → Developer Mode** → **ON**.
5. **Where notifications go** (pick one):
   - **DMs (recommended to try first):** enable Developer Mode → right‑click **your avatar** → **Copy User ID** → put it in `.env` as `DISCORD_DM_USER_ID`. After the bot is online, **send the bot any message once** so Discord opens the DM channel.
   - **Server channel:** right‑click the **text channel** → **Copy channel ID** → `DISCORD_CHANNEL_ID` (leave `DISCORD_DM_USER_ID` empty).
6. **Server:** Join **[Leo’s server](https://discord.gg/sAugS5rK)** (or use any server where you can add the bot).
7. **Add the bot** to that server (same app as in `discord_app.py`):

   ```text
   https://discord.com/oauth2/authorize?client_id=1491310298735312976&permissions=84992&scope=bot
   ```

   Or: `python -c "from discord_app import bot_invite_url; print(bot_invite_url())"`

   After the bot is in the server, you can **right‑click it in the member list → Message** to open DMs, or use a text channel for `!` commands.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # if you don’t already have one
# Edit .env: TOKEN and DISCORD_DM_USER_ID (or DISCORD_CHANNEL_ID)
python DiscordBot.py
```

### Environment (`.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `TOKEN` | Yes | Bot token from the portal (**secret**). |
| `DISCORD_DM_USER_ID` | One of two | Your user ID — bot sends episode alerts to your **DMs**. |
| `DISCORD_CHANNEL_ID` | One of two | Text channel ID — bot posts there instead. |

If both are set, **DMs** win for notifications.

### Troubleshooting

| Error | Fix |
|--------|-----|
| `PrivilegedIntentsRequired` | [Developer Portal](https://discord.com/developers/applications) → your app → **Bot** → **Privileged Gateway Intents** → enable **Message Content Intent** → **Save Changes**. Restart `DiscordBot.py`. |
| `python-dotenv could not parse` | Each `KEY=value` line must be valid: no unclosed quotes; avoid `#` inside values unless the whole value is quoted. |
| `PyNaCl` / `davey` warnings | Safe to ignore unless you add voice features. |

## Try Jikan without Discord

```bash
python scripts/jikan_season.py 2026 spring -n 5
python scripts/enrich_title.py "Jujutsu Kaisen" --url https://www.crunchyroll.com/
```

## Project layout

| Module | Role |
|--------|------|
| `DiscordBot.py` | Commands, embeds, notification loop |
| `discord_app.py` | Application ID, invite URL helper, public key (for future HTTP interactions) |
| `catalog.py` | Crunchyroll HTML snapshot + Jikan enrichment |
| `jikan_client.py` | Rate-limited Jikan HTTP client |
| `helper.py` | Config JSON, filters, schedule helpers |
| `models.py` | `Anime` dataclass |
| `config.json` | `tracking` names + `filters` genres |

## Legacy note

Older versions scraped MAL HTML and used Google search; that path was removed in favor of Jikan.
