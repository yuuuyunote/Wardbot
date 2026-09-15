"""
permissions.py
アクション実行に必要なDiscord権限のチェック。

方針転換により、招待/掲示板リンク検知のアクションはtimeoutのみになった
（delete/kick/banは廃止）。Bot招待時点で必要な権限は
チャンネルを表示・メッセージを送る・メンバーをタイムアウトの3つのみ。
"""

from typing import Optional

import discord

ACTION_PERMISSION_LABELS = {
    "timeout": "メンバーをタイムアウト",
}

_ACTION_PERMISSION_ATTR = {
    "timeout": "moderate_members",
}


def missing_permission_label(
    guild: discord.Guild,
    action: str,
    channel: Optional[discord.abc.GuildChannel] = None,
) -> Optional[str]:
    """
    指定したactionの実行に必要な権限をBotが持っているか確認する。
    持っていれば None、足りなければ日本語ラベルを返す。
    """
    if action == "none":
        return None

    attr = _ACTION_PERMISSION_ATTR.get(action)
    if attr is None:
        return None

    me = guild.me
    if me is None:
        return ACTION_PERMISSION_LABELS.get(action, action)

    perms = me.guild_permissions
    if getattr(perms, attr, False):
        return None
    return ACTION_PERMISSION_LABELS[action]