# Anime Notification Discord Bot

Discord bot that can remind a channel when tracked anime airs, with metadata from **[Jikan](https://jikan.moe/)** (unofficial MyAnimeList API).

## One-time Discord setup

Put **Application ID** (General Information) and **bot token** (Bot page) in **`.env`** — see `.env.example`. Only **`TOKEN`** is secret; the Application ID is public.

1. **[Developer Portal](https://discord.com/developers/applications)** → open your application.
2. **General Information** → copy **Application ID** into `.env` as `DISCORD_APPLICATION_ID`.
3. **Bot** → create the bot user if needed → under **Privileged Gateway Intents**, turn **Message Content Intent** **ON** → **Save Changes**. (Required or you’ll get `PrivilegedIntentsRequired` when starting the bot.)
4. **Bot** → **Reset / Copy** the token (paste into `.env` as `TOKEN`).
5. In Discord: **User Settings → Advanced → Developer Mode** → **ON**.
6. **Where notifications go** (pick one):
   - **DMs (recommended to try first):** enable Developer Mode → right‑click **your avatar** → **Copy User ID** → put it in `.env` as `DISCORD_DM_USER_ID`. After the bot is online, **send the bot any message once** so Discord opens the DM channel.
   - **Server channel:** right‑click the **text channel** → **Copy channel ID** → `DISCORD_CHANNEL_ID` (leave `DISCORD_DM_USER_ID` empty).
7. **Server:** Join **[Leo’s server](https://discord.gg/sAugS5rK)** (or use any server where you can add the bot).
8. **Add the bot** to that server (same application as `DISCORD_APPLICATION_ID` in `.env`):

   Build an invite URL (replace `YOUR_APP_ID` with `DISCORD_APPLICATION_ID` from `.env`):

   `https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&permissions=84992&scope=bot%20applications.commands`

   Or use **OAuth2 → URL Generator** in the Developer Portal (enable **`bot`** and **`applications.commands`**).

   If the bot was invited before slash commands existed, **open that URL again** and authorize so **`scope` includes `applications.commands`**.

   Optional: set **`DISCORD_GUILD_ID`** in `.env` (right‑click server → Copy Server ID) so slash commands sync **immediately** in that server; otherwise global sync can take up to ~1 hour.

   After the bot is in the server, you can **right‑click it in the member list → Message** to open DMs, or use a text channel for `!` commands.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # if you don’t already have one
# Edit .env: DISCORD_APPLICATION_ID, TOKEN, DISCORD_DM_USER_ID (or DISCORD_CHANNEL_ID)
python DiscordBot.py
```

### Docker

```bash
docker build -t anime-bot .
docker run --rm --env-file .env anime-bot
```

Mount a custom `config.json` if needed: `-v "$(pwd)/config.json:/app/config.json:ro"`.

### Tests & CI

```bash
pip install -r requirements-dev.txt
pytest
```

GitHub Actions runs the same on pushes and PRs to `main` / `master` (`.github/workflows/ci.yml`).

### Environment (`.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `DISCORD_APPLICATION_ID` | Yes | Application ID (General Information) — used for the invite link in error logs. |
| `TOKEN` | Yes | Bot token from the portal (**secret**). |
| `DISCORD_DM_USER_ID` | One of two | Your user ID — bot sends episode alerts to your **DMs**. |
| `DISCORD_CHANNEL_ID` | One of two | Text channel ID — bot posts there instead. |
| `DISCORD_GUILD_ID` | No | Server ID — if set, slash commands sync to this guild instantly. |

If both are set, **DMs** win for notifications.

### Slash commands (type `/` in chat)

| Command | What it does |
|---------|----------------|
| `/track` | Same as `!track` — add title + Jikan card. |
| `/lookup` | Same as `!lookup` — details only. |
| `/list` | Same as `!list` / `!tracked`. |
| `/ping` | Same as `!ping` — gateway latency (ms). |

### Prefix commands (`!`)

| Command | What it does |
|---------|----------------|
| `!help` / `!commands` | Lists commands. |
| `!track` / `!untrack` | Save or remove a title in `config.json`. |
| `!list` / `!tracked` | List all saved titles. |
| `!addg` / `!removeg` | Genre filters for the `!test` notify loop. |
| `!filters` | Show current genre filters. |
| `!filters clear` | Remove all genre filters. |
| `!lookup <name>` | Jikan details only — does not save. Aliases like `jjk` work. |
| `!season <year> <season>` | e.g. `!season 2026 spring`. |
| `!airing` | Top airing TV (Jikan). |
| `!test` | Demo: two fake episode embeds after ~1 minute. |
| `!ping` | Gateway latency (ms). |

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
| `DiscordBot.py` | Commands, embeds, notification loop, invite URL helper |
| `catalog.py` | Crunchyroll HTML snapshot + Jikan enrichment |
| `jikan_client.py` | Rate-limited Jikan HTTP client |
| `helper.py` | Config JSON, filters, schedule helpers |
| `models.py` | `Anime` dataclass |
| `parsing.py` | Small pure helpers (e.g. season arg parsing) |
| `config.json` | `tracking` names + `filters` genres |

## Legacy note

Older versions scraped MAL HTML and used Google search; that path was removed in favor of Jikan.
