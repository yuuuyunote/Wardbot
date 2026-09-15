"""
detection.py（デバッグ版・一時的）
report-utility-botの検知ロジック本体。

問題切り分けのため、各段階にprint()を仕込んでいる。原因が分かったら
このデバッグ版は元のバージョンに戻すこと。
"""

import re
from typing import NamedTuple, Optional

import discord

from blocklist_data import cache_for

INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:discord(?:app)?\.com/invite/(?P<code1>[a-zA-Z0-9-]+)"
    r"|(?:discord\.gg|dsc\.gg|discord\.me|discord\.io|discord\.li)/(?P<code2>[a-zA-Z0-9-]+))",
    re.IGNORECASE,
)

LISTING_SITE_PATTERNS: dict[str, re.Pattern] = {
    "disboard": re.compile(r"disboard\.org/(?:[a-z]{2}/)?server/(\d{17,20})", re.IGNORECASE),
    "dislist": re.compile(r"dislist\.net/server/(\d{17,20})", re.IGNORECASE),
    "topgg": re.compile(r"top\.gg/discord/servers/(\d{17,20})", re.IGNORECASE),
    "kokonatsu": re.compile(r"frex\.kokonatsu\.top/board/(\d{17,20})", re.IGNORECASE),
    "discom": re.compile(r"discom\.nvacod\.top/guild/(\d{17,20})", re.IGNORECASE),
    "sabachannel": re.compile(r"discord\.sabach\.jp/(?:[a-z]{2}/)?guilds/(\d{17,20})", re.IGNORECASE),
    "dicoall": re.compile(r"jp\.dicoall\.com/server/(\d{17,20})", re.IGNORECASE),
    "dissoku": re.compile(r"dissoku\.net/(?:[a-z]{2}/)?server/(\d{17,20})", re.IGNORECASE),
    "takasumibot": re.compile(r"servers\.takasumibot\.com/server/(\d{17,20})", re.IGNORECASE),
}


class ServerMatch(NamedTuple):
    guild_id: str
    matched_source: str
    entry: dict


async def find_reported_member(member: discord.Member) -> Optional[dict]:
    target_type = "bot" if member.bot else "user"
    return await cache_for(target_type).find(str(member.id))


async def find_reported_server_in_text(
    client: discord.Client, content: str
) -> Optional[ServerMatch]:
    print(f"[DEBUG] on_message content received: {content!r}")

    server_cache = cache_for("server")

    for source, pattern in LISTING_SITE_PATTERNS.items():
        m = pattern.search(content)
        if not m:
            continue
        guild_id = m.group(1)
        print(f"[DEBUG] listing-site pattern '{source}' matched, guild_id={guild_id!r}")
        try:
            entry = await server_cache.find(guild_id)
        except Exception as e:
            print(f"[DEBUG] server_cache.find() raised: {e!r}")
            raise
        print(f"[DEBUG] servers.json lookup result for {guild_id!r}: {entry!r}")
        if entry is not None:
            return ServerMatch(guild_id=guild_id, matched_source=source, entry=entry)

    for m in INVITE_RE.finditer(content):
        code = m.group("code1") or m.group("code2")
        if not code:
            continue
        print(f"[DEBUG] invite pattern matched, code={code!r}")
        try:
            invite = await client.fetch_invite(code)
        except discord.NotFound:
            print(f"[DEBUG] fetch_invite({code!r}) -> NotFound (expired/invalid, skipping)")
            continue
        except discord.HTTPException as e:
            print(f"[DEBUG] fetch_invite({code!r}) -> HTTPException: {e!r}")
            continue

        guild = invite.guild
        if guild is None:
            print(f"[DEBUG] fetch_invite({code!r}) succeeded but invite.guild is None")
            continue
        guild_id = str(guild.id)
        print(f"[DEBUG] fetch_invite({code!r}) resolved guild_id={guild_id!r}")
        try:
            entry = await server_cache.find(guild_id)
        except Exception as e:
            print(f"[DEBUG] server_cache.find() raised: {e!r}")
            raise
        print(f"[DEBUG] servers.json lookup result for {guild_id!r}: {entry!r}")
        if entry is not None:
            return ServerMatch(guild_id=guild_id, matched_source="discord-invite", entry=entry)

    print("[DEBUG] no match found, returning None")
    return None
