import asyncio
import logging
import os
import sys

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import helper
import jikan_client
from catalog import AnimeCatalog, sample_dummy_shows
from models import Anime
from discord_app import APPLICATION_ID, bot_invite_url
from helper import filter_by_genre, get_filters, get_last_episode, just_aired, rating_stars_display
from parsing import parse_season_args

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger(__name__)

REFRESH_RATE = 10

_dm_raw = os.environ.get("DISCORD_DM_USER_ID", "").strip()
_ch_raw = os.environ.get("DISCORD_CHANNEL_ID", "").strip()

DM_USER_ID: int | None = int(_dm_raw) if _dm_raw else None
CHANNEL_ID: int | None = int(_ch_raw) if _ch_raw else None

if DM_USER_ID is None and CHANNEL_ID is None:
    log.error(
        "Set DISCORD_DM_USER_ID (your user ID for DMs) or DISCORD_CHANNEL_ID in `.env` — see `.env.example`."
    )
    log.error("Invite the bot: %s", bot_invite_url())
    sys.exit(1)
if DM_USER_ID is not None and CHANNEL_ID is not None:
    log.warning(
        "Both DISCORD_DM_USER_ID and DISCORD_CHANNEL_ID are set; using DMs for notifications."
    )

intents = discord.Intents.default()
intents.message_content = True


class AnimeClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        guild_raw = os.environ.get("DISCORD_GUILD_ID", "").strip()
        if guild_raw:
            guild = discord.Object(id=int(guild_raw))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(
                "Slash commands synced to guild %s (visible immediately in that server)",
                guild_raw,
            )
        else:
            await self.tree.sync()
            log.info(
                "Slash commands synced globally — may take up to ~1h to appear; "
                "set DISCORD_GUILD_ID in .env for instant sync in one server."
            )


client = AnimeClient()


@client.tree.command(name="track", description="Add an anime to your list and fetch Jikan details.")
@app_commands.describe(title="Anime title (e.g. Jujutsu Kaisen or jjk)")
async def slash_track(interaction: discord.Interaction, title: str) -> None:
    t = title.strip()
    if not t:
        await interaction.response.send_message("Please enter a non-empty title.", ephemeral=True)
        return
    await interaction.response.defer()
    embed, plain = await run_track_flow(t)
    if embed:
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(plain or "Unknown error.")


@client.tree.command(name="lookup", description="Show Jikan details without saving to your list.")
@app_commands.describe(title="Anime title to search")
async def slash_lookup(interaction: discord.Interaction, title: str) -> None:
    t = title.strip()
    if not t:
        await interaction.response.send_message("Please enter a non-empty title.", ephemeral=True)
        return
    await interaction.response.defer()
    embed, plain = await run_lookup_flow(t)
    if embed:
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(plain or "Unknown error.")


@client.tree.command(name="list", description="List all titles you are tracking.")
async def slash_list(interaction: discord.Interaction) -> None:
    embed = build_tracked_list_embed()
    if embed is None:
        await interaction.response.send_message(
            "Your tracking list is empty. Use `/track` or `!track` to add something.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="ping", description="Check that the bot is online (gateway latency).")
async def slash_ping(interaction: discord.Interaction) -> None:
    ms = round(client.latency * 1000) if client.latency else 0
    await interaction.response.send_message(f"Pong — gateway **{ms}** ms", ephemeral=True)


@client.event
async def on_ready() -> None:
    log.info("Logged in as %s (%s)", client.user, client.user.id if client.user else "")


@tasks.loop(seconds=REFRESH_RATE)
async def check_for_updates(anime_list: list) -> None:
    filtered = filter_by_genre(anime_list, get_filters())
    log.info("filtered count: %s", len(filtered))
    for anime in list(filtered):
        if just_aired(anime):
            anime_list.remove(anime)
            log.info("notify: %s @ %s", anime.name, anime.datetime_aired)
            await send_notification(anime)
    if len(anime_list) == 0:
        check_for_updates.stop()


def build_embed(anime) -> discord.Embed:
    name = anime.name
    genres = anime.format_genres()
    rating = anime.rating or "N/A"
    link = anime.crunchyroll_url or anime.mal_url or ""
    day_s = anime.datetime_aired.strftime("%m/%d/%y") if anime.datetime_aired else "—"
    time_s = anime.datetime_aired.strftime("%I:%M %p") if anime.datetime_aired else "—"
    ep = str(get_last_episode(anime))
    score_label, stars = rating_stars_display(rating)

    embed = discord.Embed(
        title=f'Episode {ep} of "{name}" just dropped',
        description=f"Watch: {link}",
        color=0xF78C25,
    )
    embed.add_field(name="Day", value=day_s, inline=True)
    embed.add_field(name="Time (local)", value=time_s, inline=True)
    embed.add_field(name=f"Rating ({score_label}/5)", value=stars, inline=True)
    embed.add_field(name="Genres", value=genres, inline=False)
    if anime.image_url:
        embed.set_image(url=anime.image_url)
    return embed


def build_jikan_show_embed(anime: Anime, *, heading: str, description: str | None = None) -> discord.Embed:
    """Shared card for TV show details from Jikan (track / lookup)."""
    genres = anime.format_genres()
    rating = anime.rating or "N/A"
    score_label, stars = rating_stars_display(rating)
    schedule = "—"
    if anime.datetime_aired:
        schedule = anime.datetime_aired.strftime("%A • %I:%M %p (local)")
    mal = anime.mal_url or ""
    desc = description or (f"[Open on MyAnimeList]({mal})" if mal else "—")

    embed = discord.Embed(title=heading, description=desc, color=0xF78C25)
    embed.add_field(
        name="Score (MAL /10)",
        value=f"{rating} → **{score_label}/5** {stars}",
        inline=False,
    )
    embed.add_field(name="Weekly slot", value=schedule, inline=True)
    embed.add_field(name="Genres", value=genres, inline=False)
    if anime.image_url:
        embed.set_image(url=anime.image_url)
    return embed


def build_track_confirmation_embed(anime: Anime) -> discord.Embed:
    mal = anime.mal_url or ""
    desc = (
        f"[Open on MyAnimeList]({mal})"
        if mal
        else "Added to your tracking list in `config.json`."
    )
    return build_jikan_show_embed(
        anime,
        heading=f'Now tracking "{anime.name}"',
        description=desc,
    )


def build_already_tracking_embed(anime: Anime) -> discord.Embed:
    """Same Jikan card when the title was already in config (no harsh standalone line)."""
    mal = anime.mal_url or ""
    desc = (
        f"[Open on MyAnimeList]({mal})\n\nStill on your list — details refreshed from Jikan."
        if mal
        else "Still on your list in `config.json`."
    )
    return build_jikan_show_embed(
        anime,
        heading=f'Already tracking "{anime.name}"',
        description=desc,
    )


def build_lookup_embed(anime: Anime) -> discord.Embed:
    return build_jikan_show_embed(
        anime,
        heading=f'Lookup: "{anime.name}"',
        description="Jikan search + details (not saved). Use `!track` to add.",
    )


def build_help_embed() -> discord.Embed:
    """Single source of truth for !help / !commands."""
    embed = discord.Embed(
        title="Anime bot — commands",
        description="Prefix **`!`**. Jikan = public [MyAnimeList](https://myanimelist.net/) data via [jikan.moe](https://jikan.moe/).",
        color=0xF78C25,
    )
    embed.add_field(
        name="Your tracking list",
        value=(
            "**Slash:** `/track`, `/lookup`, `/list`, `/ping` (same actions; easier on mobile).\n"
            "`!track <name>` — save a title (embed refreshes from Jikan).\n"
            "`!untrack <name>` — remove from `config.json`.\n"
            "`!list` or `!tracked` — show all saved titles.\n"
            "`!addg` / `!removeg <genre>` — genre filters for the `!test` loop.\n"
            "`!filters` — show filters · `!filters clear` — remove all filters."
        ),
        inline=False,
    )
    embed.add_field(
        name="Jikan (lookup only, does not save)",
        value=(
            "`!lookup <name>` — full card without adding to your list.\n"
            "`!season <year> <season>` — e.g. `!season 2026 spring`.\n"
            "`!airing` — top airing TV on MAL."
        ),
        inline=False,
    )
    embed.add_field(
        name="Demo",
        value="`!test` — queues two fake “new episode” embeds in about a minute.",
        inline=False,
    )
    embed.add_field(
        name="Ops",
        value="`!ping` or `/ping` — gateway latency (ms).",
        inline=False,
    )
    embed.set_footer(
        text="Slash: /track /lookup /list /ping — re-invite bot with applications.commands if missing."
    )
    return embed


async def run_track_flow(arg: str) -> tuple[discord.Embed | None, str | None]:
    """Returns (embed, plain_message). One of them is set on success paths."""
    tracked = helper.get_tracked()
    already = arg in tracked
    if not already:
        if not helper.add_tracked(arg):
            return None, "Could not save to config; try again."
    show = Anime(
        name=arg,
        crunchyroll_url="https://www.crunchyroll.com/search?q="
        + arg.replace(" ", "+"),
    )
    cat = AnimeCatalog()
    try:
        ok = await asyncio.to_thread(cat.enrich_from_jikan, show)
    except Exception as exc:
        log.warning("Jikan enrich failed for track: %s", exc)
        ok = False
    if ok:
        embed = (
            build_already_tracking_embed(show)
            if already
            else build_track_confirmation_embed(show)
        )
        return embed, None
    if already:
        return None, (
            f"**{arg}** is still on your list — Jikan couldn’t load details right now."
        )
    return (
        None,
        f"Now tracking **{arg}**.\n"
        "*Couldn’t load show details from Jikan — name is saved for later.*",
    )


async def run_lookup_flow(arg: str) -> tuple[discord.Embed | None, str | None]:
    show = Anime(
        name=arg,
        crunchyroll_url="https://www.crunchyroll.com/search?q="
        + arg.replace(" ", "+"),
    )
    cat = AnimeCatalog()
    try:
        ok = await asyncio.to_thread(cat.enrich_from_jikan, show)
    except Exception as exc:
        log.warning("Jikan lookup failed: %s", exc)
        ok = False
    if ok:
        return build_lookup_embed(show), None
    return None, f"Couldn’t find a TV match on Jikan for **{arg}**."


def build_tracked_list_embed() -> discord.Embed | None:
    names = helper.get_tracked()
    if not names:
        return None
    text = "\n".join(f"• **{n}**" for n in names[:50])
    extra = f"\n… and {len(names) - 50} more." if len(names) > 50 else ""
    embed = discord.Embed(
        title="Tracked titles",
        description=text + extra,
        color=0xF78C25,
    )
    embed.set_footer(text=f"{len(names)} title(s) in config.json")
    return embed


def embed_filters_status() -> discord.Embed:
    filters = helper.get_filters()
    if not filters:
        body = "*No genre filters — the `!test` notify loop includes all genres.*"
    else:
        body = "\n".join(f"• **{g}**" for g in filters)
    return discord.Embed(
        title="Genre filters (for `!test` notify loop)",
        description=body,
        color=0xF78C25,
    )


async def send_notification(anime) -> None:
    embed = build_embed(anime)
    if DM_USER_ID is not None:
        try:
            user = await client.fetch_user(DM_USER_ID)
            await user.send(embed=embed)
        except discord.HTTPException as exc:
            log.error("Could not DM user %s: %s", DM_USER_ID, exc)
        return

    assert CHANNEL_ID is not None
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        log.error("Channel %s not found (is the bot in that server?)", CHANNEL_ID)
        return
    await channel.send(embed=embed)


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    text = message.content.strip()
    if not text.startswith("!"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    where = (
        "DM"
        if message.guild is None
        else f"{message.guild.name}/#{message.channel.name}"
    )
    log.info(
        "command cmd=%s arg=%r user=%s (%s) where=%s",
        cmd,
        arg,
        message.author.name,
        message.author.id,
        where,
    )

    if cmd == "!track":
        if not arg:
            await message.channel.send("Usage: `!track <Anime Name>` (or `/track`)")
            return
        embed, plain = await run_track_flow(arg)
        if embed:
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(plain or "Unknown error.")

    elif cmd == "!untrack":
        if not arg:
            await message.channel.send("Usage: `!untrack <Anime Name>`")
            return
        if helper.remove_tracked(arg):
            await message.channel.send(f"Stopped tracking **{arg}**.")
        else:
            await message.channel.send(f"**{arg}** is not in the tracking list.")

    elif cmd == "!addg":
        if not arg:
            await message.channel.send("Usage: `!addg <Genre>`")
            return
        if helper.add_filter(arg):
            await message.channel.send(f"Filter now includes **{arg}**.")
        else:
            await message.channel.send(f"**{arg}** is already in the filter.")

    elif cmd == "!removeg":
        if not arg:
            await message.channel.send("Usage: `!removeg <Genre>`")
            return
        if helper.remove_filter(arg):
            await message.channel.send(f"Removed **{arg}** from the filter.")
        else:
            await message.channel.send(f"**{arg}** is not in the filter.")

    elif cmd == "!lookup":
        if not arg:
            await message.channel.send("Usage: `!lookup <Anime Name>` — Jikan search, no save (or `/lookup`).")
            return
        embed, plain = await run_lookup_flow(arg)
        if embed:
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(plain or "Unknown error.")

    elif cmd == "!filters":
        sub = arg.strip().lower()
        if sub == "clear":
            helper.clear_filters()
            await message.channel.send(
                "Cleared all genre filters. The `!test` notify loop will include all genres again."
            )
        else:
            await message.channel.send(embed=embed_filters_status())

    elif cmd == "!season":
        if not arg:
            await message.channel.send(
                "Usage: `!season <year> <season>` — e.g. `!season 2026 spring` "
                "(season: winter, spring, summer, fall)."
            )
            return
        parsed = parse_season_args(arg)
        if not parsed:
            await message.channel.send(
                "Need a 4-digit year and a season: winter, spring, summer, fall."
            )
            return
        year, season = parsed
        try:
            entries = await asyncio.to_thread(
                jikan_client.season_anime, year, season
            )
        except Exception as exc:
            log.warning("Jikan season failed: %s", exc)
            await message.channel.send(f"Jikan error: `{exc}`")
            return
        entries = entries[:12]
        if not entries:
            await message.channel.send(f"No entries for **{season} {year}**.")
            return
        lines: list[str] = []
        for i, e in enumerate(entries, start=1):
            title = e.get("title") or "?"
            score = e.get("score")
            sc = f"{score}" if score is not None else "N/A"
            url = e.get("url") or ""
            line = f"**{i}.** {title} — **{sc}**/10"
            if url:
                line += f"\n<{url}>"
            lines.append(line)
        body = "\n\n".join(lines)
        if len(body) > 3800:
            body = body[:3797] + "…"
        embed = discord.Embed(
            title=f"{season.title()} {year} — seasonal (Jikan)",
            description=body,
            color=0xF78C25,
        )
        embed.set_footer(text="Data from api.jikan.moe")
        await message.channel.send(embed=embed)

    elif cmd in ("!tracked", "!list"):
        embed = build_tracked_list_embed()
        if embed is None:
            await message.channel.send(
                "Your tracking list is empty. Use `!track` or `/track` to add something."
            )
        else:
            await message.channel.send(embed=embed)

    elif cmd == "!airing":
        try:
            entries = await asyncio.to_thread(
                lambda: jikan_client.top_anime(filter_="airing", limit=10)
            )
        except Exception as exc:
            log.warning("Jikan top airing failed: %s", exc)
            await message.channel.send(f"Jikan error: `{exc}`")
            return
        if not entries:
            await message.channel.send("No data from Jikan top airing.")
            return
        lines: list[str] = []
        for i, e in enumerate(entries, start=1):
            title = e.get("title") or "?"
            score = e.get("score")
            sc = f"{score}" if score is not None else "N/A"
            url = e.get("url") or ""
            ep = e.get("episodes")
            ep_s = f"{ep} eps" if ep else "—"
            line = f"**{i}.** {title} — **{sc}**/10 · {ep_s}"
            if url:
                line += f"\n<{url}>"
            lines.append(line)
        body = "\n\n".join(lines)
        embed = discord.Embed(
            title="Top airing TV (Jikan)",
            description=body,
            color=0xF78C25,
        )
        embed.set_footer(text="Data from api.jikan.moe · filter=airing")
        await message.channel.send(embed=embed)

    elif cmd == "!test":
        await message.channel.send("Queueing 2 sample shows (airing in ~1 minute).")
        check_for_updates.start(sample_dummy_shows())

    elif cmd == "!ping":
        ms = round(client.latency * 1000) if client.latency else 0
        await message.channel.send(f"Pong — gateway **{ms}** ms")

    elif cmd in ("!help", "!commands"):
        await message.channel.send(embed=build_help_embed())


def main() -> None:
    token = os.environ.get("TOKEN")
    if not token:
        log.error("Set TOKEN in the environment.")
        sys.exit(1)
    client.run(token)


if __name__ == "__main__":
    main()
