"""
actions.py
招待/掲示板リンク検知時のアクション本体。

方針転換により、none/delete/timeout/kick/banの選択式をやめ、
「常にtimeout、timeout_minutes==0なら何もしない（ログのみ）」という
単純な形に変更した。入室検知（ユーザー/Bot）機能は一旦オフのため、
それに関する実行関数は持たない（detection.pyのfind_reported_member自体は
将来の再開に備えて残している）。
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import discord

from permissions import missing_permission_label


@dataclass
class ActionResult:
    success: bool
    timed_out: bool
    missing_permission: Optional[str] = None
    error: Optional[str] = None


async def execute_invite_timeout(message: discord.Message, timeout_minutes: int) -> ActionResult:
    """
    招待/掲示板リンク検知時に投稿者をtimeoutする。
    timeout_minutes<=0の場合は何もしない（サーバー運営の負担軽減のための無効化設定、
    ログ投稿自体は呼び出し側で必ず行う）。
    """
    if timeout_minutes <= 0:
        return ActionResult(success=True, timed_out=False)

    guild = message.guild
    if guild is None:
        return ActionResult(success=False, timed_out=False, error="guild is None")

    member = message.author
    if not isinstance(member, discord.Member):
        return ActionResult(success=False, timed_out=False, error="author is not a guild member")

    missing = missing_permission_label(guild, "timeout")
    if missing is not None:
        return ActionResult(success=False, timed_out=False, missing_permission=missing)

    try:
        await member.timeout(
            timedelta(minutes=timeout_minutes),
            reason=(
                "通報リストに登録されているサーバーの招待/掲示板リンクを投稿したため"
                f"自動timeout（{timeout_minutes}分）"
            ),
        )
    except discord.Forbidden:
        return ActionResult(
            success=False,
            timed_out=False,
            error="ロールの階層順序等により実行を拒否されました（Botのロールを対象より上位に配置してください）",
        )
    except discord.HTTPException as e:
        return ActionResult(success=False, timed_out=False, error=str(e))

    return ActionResult(success=True, timed_out=True)