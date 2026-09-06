"""
actions.py
検知後に実行するアクション本体（none/timeout/kick/ban/delete）。

権限チェックはpermissions.missing_permission_label()を実行前に必ず通す。
権限が無ければActionResult.success=Falseで、足りない権限名を
missing_permissionに入れて返す（決定④：権限不足時は明確なエラーを出す）。
discord.Forbidden（権限フラグはあるがロール階層順序等で実際には拒否された
ケース）は別途errorとして拾う。

timeoutの期間はサーバーごとに/configで設定可能（database.timeout_duration_hours）。
呼び出し側（events.py）がguild_settingsから読んだ値をtimeout_hoursとして渡す想定。
デフォルト値のDEFAULT_TIMEOUT_HOURSはdatabase.pyの初期値と合わせて24。
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import discord

from permissions import missing_permission_label

DEFAULT_TIMEOUT_HOURS = 24


@dataclass
class ActionResult:
    action: str
    success: bool
    missing_permission: Optional[str] = None
    error: Optional[str] = None


async def execute_join_action(
    member: discord.Member, action: str, timeout_hours: int = DEFAULT_TIMEOUT_HOURS
) -> ActionResult:
    """入室検知時のアクション（none/timeout/kick/ban）を実行する。"""
    if action == "none":
        return ActionResult(action=action, success=True)

    missing = missing_permission_label(member.guild, action)
    if missing is not None:
        return ActionResult(action=action, success=False, missing_permission=missing)

    try:
        if action == "timeout":
            await member.timeout(
                timedelta(hours=timeout_hours),
                reason=f"通報リストに登録されているアカウントのため自動timeout（{timeout_hours}時間）",
            )
        elif action == "kick":
            await member.kick(reason="通報リストに登録されているアカウントのため自動kick")
        elif action == "ban":
            await member.ban(
                reason="通報リストに登録されているアカウントのため自動ban",
                delete_message_seconds=0,
            )
        else:
            return ActionResult(action=action, success=False, error=f"unknown action: {action}")
    except discord.Forbidden:
        # 権限フラグ自体はあるが、Botのロールが対象より下位にある等の理由で
        # 実行時に拒否されたケース。missing_permission_labelでは検出できない。
        return ActionResult(
            action=action,
            success=False,
            error="ロールの階層順序等により実行を拒否されました（Botのロールを対象より上位に配置してください）",
        )
    except discord.HTTPException as e:
        return ActionResult(action=action, success=False, error=str(e))

    return ActionResult(action=action, success=True)


async def execute_invite_action(
    message: discord.Message, action: str, timeout_hours: int = DEFAULT_TIMEOUT_HOURS
) -> ActionResult:
    """
    招待/掲示板リンク検知時のアクション（none/delete/timeout/kick/ban）を実行する。

    deleteとtimeout/kick/banは排他的な選択肢という設計にしている
    （1サーバーにつきinvite_actionは1つだけ設定できる）。timeout/kick/banを
    選んだ場合、メッセージ自体の削除はしない（投稿者の処罰のみ）。
    """
    if action == "none":
        return ActionResult(action=action, success=True)

    guild = message.guild
    if guild is None:
        return ActionResult(action=action, success=False, error="guild is None")

    if action == "delete":
        missing = missing_permission_label(guild, action, channel=message.channel)
        if missing is not None:
            return ActionResult(action=action, success=False, missing_permission=missing)
        try:
            await message.delete()
        except discord.NotFound:
            pass  # 既に削除済みなら成功扱いでよい
        except discord.Forbidden:
            return ActionResult(action=action, success=False, error="メッセージの削除を拒否されました")
        except discord.HTTPException as e:
            return ActionResult(action=action, success=False, error=str(e))
        return ActionResult(action=action, success=True)

    # timeout/kick/ban は投稿者（GuildMember）に対して実行する
    member = message.author
    if not isinstance(member, discord.Member):
        return ActionResult(action=action, success=False, error="author is not a guild member")
    return await execute_join_action(member, action, timeout_hours=timeout_hours)
