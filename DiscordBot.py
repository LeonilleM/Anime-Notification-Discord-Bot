import asyncio
import logging
import os
import sys

import discord
from discord.ext import tasks
from dotenv import load_dotenv

import helper
from catalog import AnimeCatalog, sample_dummy_shows
from models import Anime
from discord_app import APPLICATION_ID, bot_invite_url
from helper import filter_by_genre, get_filters, get_last_episode, just_aired, rating_stars_display

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
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

client = discord.Client(intents=intents)


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


def build_track_confirmation_embed(anime: Anime) -> discord.Embed:
    """Rich preview after !track (Jikan metadata)."""
    name = anime.name
    genres = anime.format_genres()
    rating = anime.rating or "N/A"
    score_label, stars = rating_stars_display(rating)
    schedule = "—"
    if anime.datetime_aired:
        schedule = anime.datetime_aired.strftime("%A • %I:%M %p (local)")
    mal = anime.mal_url or ""
    desc = f"[Open on MyAnimeList]({mal})" if mal else "Added to your tracking list in `config.json`."

    embed = discord.Embed(
        title=f'Now tracking "{name}"',
        description=desc,
        color=0xF78C25,
    )
    embed.add_field(name="Score (MAL /10)", value=f"{rating} → **{score_label}/5** {stars}", inline=False)
    embed.add_field(name="Weekly slot", value=schedule, inline=True)
    embed.add_field(name="Genres", value=genres, inline=False)
    if anime.image_url:
        embed.set_image(url=anime.image_url)
    return embed


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

    if cmd == "!track":
        if not arg:
            await message.channel.send("Usage: `!track <Anime Name>`")
            return
        if not helper.add_tracked(arg):
            await message.channel.send(f"**{arg}** is already tracked.")
            return
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
            await message.channel.send(embed=build_track_confirmation_embed(show))
        else:
            await message.channel.send(
                f"Now tracking **{arg}**.\n"
                "*Couldn’t load show details from Jikan — name is saved for later.*"
            )

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

    elif cmd == "!test":
        await message.channel.send("Queueing 2 sample shows (airing in ~1 minute).")
        check_for_updates.start(sample_dummy_shows())

    elif cmd == "!help":
        embed = discord.Embed(title="Commands", color=0xF78C25)
        embed.add_field(
            name="!track <name>",
            value="Add a title; bot replies with a Jikan preview embed when lookup succeeds.",
            inline=False,
        )
        embed.add_field(
            name="!untrack <name>", value="Remove a title from tracking.", inline=False
        )
        embed.add_field(
            name="!addg / !removeg <genre>",
            value="Restrict notifications to these genres (empty = all).",
            inline=False,
        )
        embed.add_field(
            name="!test",
            value="Send two fake notifications after ~1 minute.",
            inline=False,
        )
        await message.channel.send(embed=embed)


def main() -> None:
    token = os.environ.get("TOKEN")
    if not token:
        log.error("Set TOKEN in the environment.")
        sys.exit(1)
    client.run(token)


if __name__ == "__main__":
    main()
