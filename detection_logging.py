"""
detection_logging.py
検知結果をComponents V2（discord.ui.LayoutView）で組み立て、各サーバーの
ログチャンネル＋開発者用横断チャンネル（DEV_LOG_CHANNEL_ID）へリアルタイム
投稿する。DBには保存しない。

方針転換により、アクションはtimeoutのみ（0分＝無効化）になったため、
ActionResultの表示ロジックもそれに合わせて簡略化している。

sender: 招待/掲示板リンク検知でのみ使う。「誰がそのリンクを投稿したか」を
ログに残すための情報。
"""

import os
from typing import Optional

import discord

from actions import ActionResult
from category_labels import label_for

DEV_LOG_CHANNEL_ID = os.getenv("DEV_LOG_CHANNEL_ID")


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
    accent = discord.Colour.orange() if action_result.success else discord.Colour.red()

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

    if action_result.missing_permission:
        lines.append(
            f"**⚠️ タイムアウト未実行（権限不足）**: Botに「{action_result.missing_permission}」権限がありません"
        )
    elif not action_result.success:
        lines.append(f"**⚠️ タイムアウト未実行（エラー）**: {action_result.error or '不明なエラー'}")
    elif action_result.timed_out:
        lines.append("**投稿者をタイムアウトしました**")
    else:
        lines.append("**タイムアウトは無効化されています（ログのみ）**")

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
    """
    サーバー側のログチャンネル（設定されていれば）と、開発者用横断チャンネル
    （DEV_LOG_CHANNEL_ID、設定されていれば）の両方に検知ログを投稿する。
    片方の投稿が失敗してももう片方には影響しないよう個別にtry/exceptしている。
    """
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