"""
detection.py
report-utility-botの検知ロジック本体。

1. find_reported_member() — 入室検知。member.botフラグでusers.json/bots.jsonを
   使い分ける（xgomi-discord側で通報時点からuser/botは別データとして
   登録されているため、ここでも同じ区別を踏襲する）。

2. find_reported_server_in_text() — メッセージ本文から
   (a) Discord公式招待リンク（discord.gg等、複数ドメインバリエーション）
   (b) サーバー掲示板サイトの直リンク（URLにサーバーIDがそのまま入っている9サイト）
   を検出し、servers.jsonと突合する。

   公式招待リンクはコードだけでは対象サーバーが分からないため
   `client.fetch_invite()`で解決する必要がある。期限切れ・無効な招待は
   `discord.NotFound`になるが、この場合は検知対象外（設計判断通り、
   何もしない）。

   掲示板サイト直リンクはURL自体にサーバーIDが書かれているため、
   APIを叩かずに即座に照合できる。

   「対応不可（サーバーIDなし）」5サイト（鯖缶・DCafe・Shark bot・Discordme・
   Discadia）はページのスクレイピングが必要になり、サイト構造変化に弱く
   利用規約的にもグレーになりやすいため、MVPでは対応しない。
"""

import re
from typing import NamedTuple, Optional

import discord

from blocklist_data import cache_for

# Discord公式招待リンクのドメインバリエーション。
# discord.com/invite/ と discordapp.com/invite/（レガシー）は "/invite/" が要る形式、
# それ以外（discord.gg, dsc.gg, discord.me, discord.io, discord.li）はコードが
# ドメイン直後に来る形式。
INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:discord(?:app)?\.com/invite/(?P<code1>[a-zA-Z0-9-]+)"
    r"|(?:discord\.gg|dsc\.gg|discord\.me|discord\.io|discord\.li)/(?P<code2>[a-zA-Z0-9-]+))",
    re.IGNORECASE,
)

# サーバーID直リンク型の掲示板サイト（本人確認済みの9サイト）。
# キーはmatched_sourceとしてログに出す識別子。
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
    matched_source: str  # 'discord-invite' | 'disboard' | 'dislist' | ... (LISTING_SITE_PATTERNSのキー)
    entry: dict  # servers.json内の該当エントリ（categories, note等を含む）


async def find_reported_member(member: discord.Member) -> Optional[dict]:
    """
    入室してきたメンバーが通報リストに載っているか確認する。
    Botアカウントならbots.json、通常ユーザーならusers.jsonを参照する。
    載っていなければNone。
    """
    target_type = "bot" if member.bot else "user"
    return await cache_for(target_type).find(str(member.id))


async def find_reported_server_in_text(
    client: discord.Client, content: str
) -> Optional[ServerMatch]:
    """
    メッセージ本文中の招待リンク・掲示板サイトリンクを検出し、通報済みサーバーに
    一致すればServerMatchを返す。複数マッチしても最初に見つかった1件のみ返す
    （同一メッセージに複数の悪質サーバー言及が同時に含まれるケースは稀と想定し、
    シンプルさを優先）。
    """
    server_cache = cache_for("server")

    # 1. 掲示板サイト直リンク（APIを叩かず即照合できるので先に処理する）
    for source, pattern in LISTING_SITE_PATTERNS.items():
        m = pattern.search(content)
        if not m:
            continue
        guild_id = m.group(1)
        entry = await server_cache.find(guild_id)
        if entry is not None:
            return ServerMatch(guild_id=guild_id, matched_source=source, entry=entry)

    # 2. Discord公式招待リンク（コードを実際に解決しないとguild idが分からない）
    for m in INVITE_RE.finditer(content):
        code = m.group("code1") or m.group("code2")
        if not code:
            continue
        try:
            invite = await client.fetch_invite(code)
        except discord.NotFound:
            continue  # 期限切れ・無効な招待は検知対象外（設計判断通り）
        except discord.HTTPException:
            continue  # 一時的なAPIエラー等。ここで例外を投げてイベントループを止めない

        guild = invite.guild
        if guild is None:
            continue
        guild_id = str(guild.id)
        entry = await server_cache.find(guild_id)
        if entry is not None:
            return ServerMatch(guild_id=guild_id, matched_source="discord-invite", entry=entry)

    return None
