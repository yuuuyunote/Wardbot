"""
config.py
サーバー管理者向けの設定コマンド。/config グループの下にサブコマンドを持つ。

Groupのdefault_permissionsにより、既定では「サーバー管理」権限を持つ
メンバーにのみコマンドが見える（サーバー側の統合設定でさらに絞ることも可能）。

権限が無い状態でアクションを設定しようとしても保存自体は拒否しない
（後から権限を付与する運用を想定）。ただし決定①の通り、その場で
「この設定には○○権限が必要です」という案内を添える。

timeout_duration: サーバーごとにtimeout時間を設定できる。範囲は
database.MIN_TIMEOUT_HOURS〜MAX_TIMEOUT_HOURS（1〜672時間 = Discordの
timeout仕様上の上限28日）。

重要: database.pyの関数はpsycopg2（同期・ブロッキング）で書かれている。
discord.pyの非同期イベントループ上でこれを直接awaitなしに呼ぶと
イベントループ全体（Discordのgatewayも含む）が止まり、Interactionの
3秒応答期限に間に合わなくなる（実際にこれが原因で「アプリケーションが
応答しません」が発生した）。そのため、必ず
  1. 先にinteraction.response.defer()で応答期限を15分に延長する
  2. database.*の呼び出しはasyncio.to_thread()で別スレッドに逃がす
の2点を徹底する。xgomi-discord側のbot/reports/db.pyと同じ設計方針。
"""

import asyncio
from typing import Literal, Optional

import discord
from discord import app_commands

import database
from permissions import missing_permission_label

JoinAction = Literal["none", "timeout", "kick", "ban"]
InviteAction = Literal["none", "delete", "timeout", "kick", "ban"]

_JOIN_ACTION_LABELS = {"none": "何もしない", "timeout": "タイムアウト", "kick": "キック", "ban": "BAN"}
_INVITE_ACTION_LABELS = {
    "none": "何もしない",
    "delete": "メッセージを削除",
    "timeout": "タイムアウト",
    "kick": "キック",
    "ban": "BAN",
}


class ConfigGroup(app_commands.Group):
    def __init__(self) -> None:
        super().__init__(
            name="config",
            description="このサーバーでの検知時の挙動を設定する",
            default_permissions=discord.Permissions(manage_guild=True),
        )

    @app_commands.command(name="join_action", description="入室検知時のデフォルトアクションを設定する")
    @app_commands.describe(action="入室検知時に自動実行するアクション")
    async def join_action(self, interaction: discord.Interaction, action: JoinAction) -> None:
        await interaction.response.defer(ephemeral=True)

        await asyncio.to_thread(database.set_join_action, str(interaction.guild_id), action)

        missing = missing_permission_label(interaction.guild, action)
        label = _JOIN_ACTION_LABELS[action]
        if missing:
            await interaction.followup.send(
                f"入室検知時のアクションを「{label}」に設定しました。\n"
                f"⚠️ 現在Botに「{missing}」権限が無いため、検知が発生してもこのアクションは実行できません。"
                "サーバー設定でBotのロールに権限を付与してください。",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"入室検知時のアクションを「{label}」に設定しました。", ephemeral=True
            )

    @app_commands.command(
        name="invite_action", description="招待/掲示板リンク検知時のデフォルトアクションを設定する"
    )
    @app_commands.describe(action="招待/掲示板リンク検知時に自動実行するアクション")
    async def invite_action(self, interaction: discord.Interaction, action: InviteAction) -> None:
        await interaction.response.defer(ephemeral=True)

        await asyncio.to_thread(database.set_invite_action, str(interaction.guild_id), action)

        missing = missing_permission_label(interaction.guild, action)
        label = _INVITE_ACTION_LABELS[action]
        if missing:
            await interaction.followup.send(
                f"招待/掲示板リンク検知時のアクションを「{label}」に設定しました。\n"
                f"⚠️ 現在Botに「{missing}」権限が無いため、検知が発生してもこのアクションは実行できません。"
                "サーバー設定でBotのロールに権限を付与してください。",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"招待/掲示板リンク検知時のアクションを「{label}」に設定しました。", ephemeral=True
            )

    @app_commands.command(name="log_channel", description="検知ログを投稿するチャンネルを設定する")
    @app_commands.describe(channel="検知ログの投稿先チャンネル（省略すると解除）")
    async def log_channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        await asyncio.to_thread(
            database.set_log_channel, str(interaction.guild_id), str(channel.id) if channel else None
        )

        if channel is None:
            await interaction.followup.send("検知ログの投稿先を解除しました。", ephemeral=True)
            return

        perms = channel.permissions_for(interaction.guild.me)
        if not perms.send_messages:
            await interaction.followup.send(
                f"検知ログの投稿先を{channel.mention}に設定しました。\n"
                "⚠️ ただしBotがこのチャンネルにメッセージを送信する権限を持っていないため、"
                "このままでは投稿できません。チャンネル権限を確認してください。",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"検知ログの投稿先を{channel.mention}に設定しました。", ephemeral=True
            )

    @app_commands.command(
        name="timeout_duration", description="timeoutアクションを実行する際の時間（時間単位）を設定する"
    )
    @app_commands.describe(
        hours=f"timeout時間（{database.MIN_TIMEOUT_HOURS}〜{database.MAX_TIMEOUT_HOURS}時間、Discord仕様上の上限は28日）"
    )
    async def timeout_duration(
        self,
        interaction: discord.Interaction,
        hours: app_commands.Range[int, database.MIN_TIMEOUT_HOURS, database.MAX_TIMEOUT_HOURS],
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        await asyncio.to_thread(database.set_timeout_duration, str(interaction.guild_id), hours)

        await interaction.followup.send(f"timeout時間を{hours}時間に設定しました。", ephemeral=True)

    @app_commands.command(name="show", description="現在のこのサーバーの設定を表示する")
    async def show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        settings = await asyncio.to_thread(database.get_guild_settings, str(interaction.guild_id))

        log_channel_mention = (
            f"<#{settings['log_channel_id']}>" if settings["log_channel_id"] else "（未設定）"
        )
        lines = [
            f"入室検知時のアクション: {_JOIN_ACTION_LABELS.get(settings['join_action'], settings['join_action'])}",
            f"招待/掲示板リンク検知時のアクション: "
            f"{_INVITE_ACTION_LABELS.get(settings['invite_action'], settings['invite_action'])}",
            f"timeout時間: {settings['timeout_duration_hours']}時間",
            f"検知ログ投稿先: {log_channel_mention}",
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)
