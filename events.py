"""
events.py
Botのgatewayイベントハンドラ。

- on_message: 招待/掲示板リンク検知 → メッセージ削除（常に試行）＋タイムアウト
  （0分なら省略）→ ログ投稿
- on_guild_join / on_guild_remove: 導入・削除の通知（開発者用チャンネル）

入室検知（ユーザー/Bot）は一旦オフ。detection.pyのfind_reported_member自体は
残しているので、再開時はここにon_member_joinを足すだけで良い。

database.get_guild_settings()はasyncio.to_thread()で別スレッドに逃がす
（イベントループ・ハートビートを止めないため）。
"""

import asyncio

import discord

import database
from actions import execute_invite_response
from detection import find_reported_server_in_text
from detection_logging import post_detection_log
from guild_join_logging import post_guild_join_log, post_guild_leave_log


def setup_events(client: discord.Client) -> None:
    @client.event
    async def on_guild_join(guild: discord.Guild) -> None:
        await post_guild_join_log(client, guild)

    @client.event
    async def on_guild_remove(guild: discord.Guild) -> None:
        await post_guild_leave_log(client, guild)

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        match = await find_reported_server_in_text(client, message.content)
        if match is None:
            return

        settings = await asyncio.to_thread(database.get_guild_settings, str(message.guild.id))

        result = await execute_invite_response(
            message, timeout_minutes=settings["timeout_duration_minutes"]
        )

        await post_detection_log(
            client,
            guild=message.guild,
            log_channel_id=settings["log_channel_id"],
            target_type="server",
            target_id=match.guild_id,
            categories=match.entry.get("categories", []),
            note=match.entry.get("note", ""),
            action_result=result,
            matched_source=match.matched_source,
            sender=message.author,
        )
