"""
commands.py
report-utility-botのスラッシュコマンド一式。

方針転換により /join_action・/invite_action は廃止。挙動は
/timeout_duration（0で無効化＝ログのみ）と/log_channelだけで制御する。

/timeout_duration・/log_channel・/setting_show は
default_permissions(manage_guild=True)で、既定では「サーバー管理」権限を
持つメンバーにのみ見える。/help のみ全員に見せる。

database.pyの呼び出しはpsycopg2（同期・ブロッキング）なので、必ず
asyncio.to_thread()で別スレッドに逃がす。
"""

import asyncio
from typing import Optional

import discord
from discord import app_commands

import database
from duration import format_minutes, parse_duration_to_minutes
from embeds import BRAND_COLOR, error_embed, info_embed, success_embed, warning_embed
from permissions import missing_permission_label

GUIDE_BASE_PLUS_INVITE_URL = "https://discord.gg/qzBm9aMWss"


def setup_commands(tree: app_commands.CommandTree) -> None:
    @tree.command(name="log_channel", description="検知ログを投稿するチャンネルを設定する")
    @app_commands.describe(channel="検知ログの投稿先チャンネル（省略すると解除）")
    @app_commands.default_permissions(manage_guild=True)
    async def log_channel(
        interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await asyncio.to_thread(
            database.set_log_channel, str(interaction.guild_id), str(channel.id) if channel else None
        )

        if channel is None:
            await interaction.followup.send(
                embed=success_embed("検知ログの投稿先を解除しました"), ephemeral=True
            )
            return

        perms = channel.permissions_for(interaction.guild.me)
        if not perms.send_messages:
            embed = warning_embed(
                "検知ログの投稿先を設定しました",
                f"投稿先: {channel.mention}\n\n"
                "Botがこのチャンネルにメッセージを送信する権限を持っていないため、"
                "このままでは投稿できません。チャンネル権限を確認してください。",
            )
        else:
            embed = success_embed("検知ログの投稿先を設定しました", f"投稿先: {channel.mention}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(
        name="timeout_duration",
        description="招待/掲示板リンク検知時のタイムアウト時間を設定する（0で無効化）",
    )
    @app_commands.describe(duration="タイムアウト時間（例: 10m, 2h, 3d）。「0」で無効化（ログのみ）")
    @app_commands.default_permissions(manage_guild=True)
    async def timeout_duration(interaction: discord.Interaction, duration: str) -> None:
        try:
            minutes = parse_duration_to_minutes(duration)
        except ValueError as e:
            await interaction.response.send_message(
                embed=error_embed("設定に失敗しました", str(e)), ephemeral=True
            )
            return

        if minutes != 0 and not (database.MIN_TIMEOUT_MINUTES <= minutes <= database.MAX_TIMEOUT_MINUTES):
            await interaction.response.send_message(
                embed=error_embed(
                    "設定に失敗しました",
                    f"timeout時間は0（無効化）または{format_minutes(database.MIN_TIMEOUT_MINUTES)}〜"
                    f"{format_minutes(database.MAX_TIMEOUT_MINUTES)}の範囲で指定してください"
                    "（Discord仕様上の上限は28日）。",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await asyncio.to_thread(database.set_timeout_duration, str(interaction.guild_id), minutes)
        await interaction.followup.send(
            embed=success_embed("タイムアウト時間を設定しました", f"設定: **{format_minutes(minutes)}**"),
            ephemeral=True,
        )

    @tree.command(name="setting_show", description="現在のこのサーバーの設定を表示する")
    @app_commands.default_permissions(manage_guild=True)
    async def setting_show(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await asyncio.to_thread(database.get_guild_settings, str(interaction.guild_id))

        log_channel_text = (
            f"<#{settings['log_channel_id']}>" if settings["log_channel_id"] else "未設定"
        )

        embed = info_embed("現在の設定")
        embed.add_field(
            name="タイムアウト時間",
            value=format_minutes(settings["timeout_duration_minutes"]),
            inline=True,
        )
        embed.add_field(name="検知ログ投稿先", value=log_channel_text, inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="help", description="使い方・サポートサーバー・通報方法などを表示する")
    async def help_command(interaction: discord.Interaction) -> None:
        view = discord.ui.LayoutView()
        container = discord.ui.Container(accent_color=BRAND_COLOR)

        container.add_item(discord.ui.TextDisplay("## Wardの使い方"))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Botに関するサポートや検知（危険）リストへの追加、解除申請は "
                "Guide Base + サーバーよりできます。"
            )
        )
        container.add_item(
            discord.ui.ActionRow(
                discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    url=GUIDE_BASE_PLUS_INVITE_URL,
                    label="Guide Base + に参加",
                )
            )
        )
        container.add_item(discord.ui.TextDisplay("**設定コマンド（サーバー管理権限が必要）**"))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "`/log_channel` — 検知ログの投稿先チャンネルを設定\n"
                "`/timeout_duration` — 招待/掲示板リンク検知時のタイムアウト時間を設定"
                "（例: 10m, 2h, 3d。「0」で無効化）\n"
                "`/setting_show` — 現在の設定を表示"
            )
        )

        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)