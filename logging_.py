"""
logging.py
検知結果をComponents V2（discord.ui.LayoutView）で組み立て、各サーバーの
ログチャンネル＋開発者用横断チャンネル（DEV_LOG_CHANNEL_ID）へリアルタイム
投稿する。DBには保存しない（決定通り、チャンネル投稿のみで完結させる）。

Components V2はdiscord.py 2.6+で利用可能。同じメッセージ内でcontent/embed/
sticker/pollとは併用できないため、view=のみで送信する。
"""

import os
from typing import Optional

import discord

from actions import ActionResult
from category_labels import label_for

DEV_LOG_CHANNEL_ID = os.getenv("DEV_LOG_CHANNEL_ID")

_ACTION_RESULT_LABELS = {
    "none": "何もしない（警告のみ）",
    "delete": "メッセージを削除",
    "timeout": "タイムアウト",
    "kick": "キック",
    "ban": "BAN",
}

_DETECTION_TYPE_LABELS = {
    "join": "入室検知",
    "invite": "招待/掲示板リンク検知",
}


def _build_log_view(
    *,
    detection_type: str,
    target_type: str,
    target_id: str,
    categories: list[str],
    note: str,
    action_result: ActionResult,
    matched_source: Optional[str] = None,
    guild_name: Optional[str] = None,
) -> discord.ui.LayoutView:
    """
    検知結果1件分のComponents V2レイアウトを組み立てる。
    guild_nameを渡した場合のみ「どのサーバーで発生したか」の行を足す
    （開発者用横断ログでのみ使う）。
    """
    accent = discord.Colour.orange() if action_result.success else discord.Colour.red()

    view = discord.ui.LayoutView()
    container = discord.ui.Container(accent_color=accent)

    header = f"## ⚠️ {_DETECTION_TYPE_LABELS.get(detection_type, detection_type)}"
    container.add_item(discord.ui.TextDisplay(header))
    container.add_item(discord.ui.Separator())

    lines = [f"**対象ID**: `{target_id}`（{target_type}）"]
    if guild_name is not None:
        lines.append(f"**発生サーバー**: {guild_name}")
    if matched_source is not None:
        lines.append(f"**検知経路**: {matched_source}")

    labels = "、".join(label_for(c, target_type) for c in categories) if categories else "（不明）"
    lines.append(f"**カテゴリ**: {labels}")
    lines.append(f"**補足**: {note or '（なし）'}")

    if action_result.success:
        action_label = _ACTION_RESULT_LABELS.get(action_result.action, action_result.action)
        lines.append(f"**実行したアクション**: {action_label}")
    elif action_result.missing_permission:
        lines.append(
            f"**⚠️ アクション未実行（権限不足）**: Botに「{action_result.missing_permission}」権限がありません"
        )
    else:
        lines.append(f"**⚠️ アクション未実行（エラー）**: {action_result.error or '不明なエラー'}")

    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    view.add_item(container)
    return view


async def post_detection_log(
    client: discord.Client,
    *,
    guild: discord.Guild,
    log_channel_id: Optional[str],
    detection_type: str,
    target_type: str,
    target_id: str,
    categories: list[str],
    note: str,
    action_result: ActionResult,
    matched_source: Optional[str] = None,
) -> None:
    """
    サーバー側のログチャンネル（設定されていれば）と、開発者用横断チャンネル
    （DEV_LOG_CHANNEL_ID、設定されていれば）の両方に検知ログを投稿する。
    どちらも未設定なら何もしない。片方の投稿が失敗してももう片方には
    影響しないよう個別にtry/exceptしている（ログ投稿の失敗で検知処理
    全体を止めない）。
    """
    if log_channel_id:
        try:
            channel = client.get_channel(int(log_channel_id)) or await client.fetch_channel(
                int(log_channel_id)
            )
            view = _build_log_view(
                detection_type=detection_type,
                target_type=target_type,
                target_id=target_id,
                categories=categories,
                note=note,
                action_result=action_result,
                matched_source=matched_source,
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
                detection_type=detection_type,
                target_type=target_type,
                target_id=target_id,
                categories=categories,
                note=note,
                action_result=action_result,
                matched_source=matched_source,
                guild_name=f"{guild.name}（`{guild.id}`）",
            )
            await dev_channel.send(view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            pass
