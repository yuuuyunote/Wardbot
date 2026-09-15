"""
detection_logging.py
検知結果をComponents V2（discord.ui.LayoutView）で組み立て、各サーバーの
ログチャンネル＋開発者用横断チャンネル（DEV_LOG_CHANNEL_ID）へリアルタイム
投稿する。DBには保存しない。

削除・timeoutは独立した結果を持つため、ログ表示も別々の行にしている。
"""

import os
from typing import Optional

import discord

from actions import ActionResult
from category_labels import label_for

DEV_LOG_CHANNEL_ID = os.getenv("DEV_LOG_CHANNEL_ID")


def _delete_line(action_result: ActionResult) -> str:
    if action_result.deleted:
        return "**メッセージ削除**: 実行しました"
    if action_result.delete_missing_permission:
        return f"**⚠️ メッセージ削除未実行（権限不足）**: Botに「{action_result.delete_missing_permission}」権限がありません"
    return f"**⚠️ メッセージ削除未実行（エラー）**: {action_result.delete_error or '不明なエラー'}"


def _timeout_line(action_result: ActionResult) -> str:
    if action_result.timeout_skipped:
        return "**タイムアウト**: 無効化されています（設定で0分）"
    if action_result.timed_out:
        return "**タイムアウト**: 実行しました"
    if action_result.timeout_missing_permission:
        return f"**⚠️ タイムアウト未実行（権限不足）**: Botに「{action_result.timeout_missing_permission}」権限がありません"
    return f"**⚠️ タイムアウト未実行（エラー）**: {action_result.timeout_error or '不明なエラー'}"


def _build_log_view(
    *,
    target_type: str,
    target_id: str,
    categories: list[str],
    note: str,
    action_result: ActionResult,
    matched_source: Optional[str] = None,
    guild_name: Optional[str] = None,
    sender: Optional[discord.abc.User] = None,
) -> discord.ui.LayoutView:
    all_ok = action_result.deleted and (action_result.timed_out or action_result.timeout_skipped)
    accent = discord.Colour.orange() if all_ok else discord.Colour.red()

    view = discord.ui.LayoutView()
    container = discord.ui.Container(accent_color=accent)

    container.add_item(discord.ui.TextDisplay("## ⚠️ 招待/掲示板リンク検知"))
    container.add_item(discord.ui.Separator())

    lines = [f"**対象ID**: `{target_id}`（{target_type}）"]
    if guild_name is not None:
        lines.append(f"**発生サーバー**: {guild_name}")
    if sender is not None:
        lines.append(f"**投稿者**: {sender.mention}（`{sender.id}`）")
    if matched_source is not None:
        lines.append(f"**検知経路**: {matched_source}")

    labels = "、".join(label_for(c, target_type) for c in categories) if categories else "（不明）"
    lines.append(f"**カテゴリ**: {labels}")
    lines.append(f"**補足**: {note or '（なし）'}")

    lines.append(_delete_line(action_result))
    lines.append(_timeout_line(action_result))

    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    view.add_item(container)
    return view


async def post_detection_log(
    client: discord.Client,
    *,
    guild: discord.Guild,
    log_channel_id: Optional[str],
    target_type: str,
    target_id: str,
    categories: list[str],
    note: str,
    action_result: ActionResult,
    matched_source: Optional[str] = None,
    sender: Optional[discord.abc.User] = None,
) -> None:
    if log_channel_id:
        try:
            channel = client.get_channel(int(log_channel_id)) or await client.fetch_channel(
                int(log_channel_id)
            )
            view = _build_log_view(
                target_type=target_type,
                target_id=target_id,
                categories=categories,
                note=note,
                action_result=action_result,
                matched_source=matched_source,
                sender=sender,
            )
            await channel.send(view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            pass

    if DEV_LOG_CHANNEL_ID:
        try:
            dev_channel = client.get_channel(int(DEV_LOG_CHANNEL_ID)) or await client.fetch_channel(
                int(DEV_LOG_CHANNEL_ID)
            )
            view = _build_log_view(
                target_type=target_type,
                target_id=target_id,
                categories=categories,
                note=note,
                action_result=action_result,
                matched_source=matched_source,
                guild_name=f"{guild.name}（`{guild.id}`）",
                sender=sender,
            )
            await dev_channel.send(view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            pass
