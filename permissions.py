"""
permissions.py
アクション実行に必要なDiscord権限のチェック。

招待/掲示板リンク検知は「削除（常に試行）＋timeout（0分なら省略）」の
2アクション構成。deleteはチャンネル単位の権限上書きがあり得るため
channel.permissions_for()、timeoutはギルド単位の権限なのでguild.me.guild_permissions
で判定する。
"""

from typing import Optional

import discord

ACTION_PERMISSION_LABELS = {
    "delete": "メッセージの管理",
    "timeout": "メンバーをタイムアウト",
}

_ACTION_PERMISSION_ATTR = {
    "delete": "manage_messages",
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

    if action == "delete" and channel is not None:
        perms = channel.permissions_for(me)
    else:
        perms = me.guild_permissions

    if getattr(perms, attr, False):
        return None
    return ACTION_PERMISSION_LABELS[action]
