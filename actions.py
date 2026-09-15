"""
actions.py
招待/掲示板リンク検知時のアクション本体。

検知したら常に「メッセージ削除」を試行し、加えて timeout_minutes > 0 なら
投稿者をtimeoutする（0なら削除のみでtimeoutは行わない）。削除とtimeoutは
互いに独立した結果を持つ（片方が権限不足で失敗しても、もう片方の結果には
影響しない）。

入室検知（ユーザー/Bot）は一旦オフのため、それに関する実行関数は持たない。
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import discord

from permissions import missing_permission_label

@dataclass
class ActionResult:
    deleted: bool = False
    delete_missing_permission: Optional[str] = None
    delete_error: Optional[str] = None

    timed_out: bool = False
    timeout_skipped: bool = False  # timeout_minutes<=0で意図的にスキップした場合
    timeout_missing_permission: Optional[str] = None
    timeout_error: Optional[str] = None


async def execute_invite_response(message: discord.Message, timeout_minutes: int) -> ActionResult:
    """
    招待/掲示板リンク検知時の対応。
    1. メッセージ削除（常に試行）
    2. timeout_minutes > 0 の場合のみ、投稿者をtimeoutする
    """
    result = ActionResult()

    guild = message.guild
    if guild is None:
        result.delete_error = "guild is None"
        result.timeout_error = "guild is None"
        return result

    # 1. メッセージ削除（常に試行）
    missing_delete = missing_permission_label(guild, "delete", channel=message.channel)
    if missing_delete is not None:
        result.delete_missing_permission = missing_delete
    else:
        try:
            await message.delete()
            result.deleted = True
        except discord.NotFound:
            result.deleted = True  # 既に削除済みなら成功扱いでよい
        except discord.Forbidden:
            result.delete_error = "メッセージの削除を拒否されました"
        except discord.HTTPException as e:
            result.delete_error = str(e)

    # 2. timeout（0以下なら意図的にスキップ＝サーバー運営の負担軽減設定）
    if timeout_minutes <= 0:
        result.timeout_skipped = True
        return result

    member = message.author
    if not isinstance(member, discord.Member):
        result.timeout_error = "author is not a guild member"
        return result

    missing_timeout = missing_permission_label(guild, "timeout")
    if missing_timeout is not None:
        result.timeout_missing_permission = missing_timeout
        return result

    try:
        await member.timeout(
            timedelta(minutes=timeout_minutes),
            reason=(
                "通報リストに登録されているサーバーの招待/掲示板リンクを投稿したため"
                f"自動timeout（{timeout_minutes}分）"
            ),
        )
        result.timed_out = True
    except discord.Forbidden:
        result.timeout_error = (
            "ロールの階層順序等により実行を拒否されました（Botのロールを対象より上位に配置してください）"
        )
    except discord.HTTPException as e:
        result.timeout_error = str(e)

    return result
