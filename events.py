"""
events.py
Botのgatewayイベントハンドラ。検知 → デフォルトアクション実行 → ログ投稿、
という一連の流れをここでつなぐ。

on_member_join: members Intentが必須。
on_message: message_content Intentが必須（本文から招待/掲示板リンクを
探すため）。

timeout_hoursはguild_settings.timeout_duration_hours（/configで変更可能）
をそのまま各アクション実行関数に渡す。
"""

import discord

import database
from actions import execute_invite_action, execute_join_action
from detection import find_reported_member, find_reported_server_in_text
from detection_logging import post_detection_log


def setup_events(client: discord.Client) -> None:
    @client.event
    async def on_member_join(member: discord.Member) -> None:
        entry = await find_reported_member(member)
        if entry is None:
            return

        settings = database.get_guild_settings(str(member.guild.id))
        action = settings["join_action"]
        target_type = "bot" if member.bot else "user"

        result = await execute_join_action(
            member, action, timeout_hours=settings["timeout_duration_hours"]
        )

        await post_detection_log(
            client,
            guild=member.guild,
            log_channel_id=settings["log_channel_id"],
            detection_type="join",
            target_type=target_type,
            target_id=str(member.id),
            categories=entry.get("categories", []),
            note=entry.get("note", ""),
            action_result=result,
        )

    @client.event
    async def on_message(message: discord.Message) -> None:
        # Botのメッセージ（自分自身含む）とDMは対象外
        if message.author.bot or message.guild is None:
            return

        match = await find_reported_server_in_text(client, message.content)
        if match is None:
            return

        settings = database.get_guild_settings(str(message.guild.id))
        action = settings["invite_action"]

        result = await execute_invite_action(
            message, action, timeout_hours=settings["timeout_duration_hours"]
        )

        await post_detection_log(
            client,
            guild=message.guild,
            log_channel_id=settings["log_channel_id"],
            detection_type="invite",
            target_type="server",
            target_id=match.guild_id,
            categories=match.entry.get("categories", []),
            note=match.entry.get("note", ""),
            action_result=result,
            matched_source=match.matched_source,
        )
