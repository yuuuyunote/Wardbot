"""
permissions.py
アクション実行に必要なDiscord権限のチェック。

Bot招待URLは最小権限（0）で発行する設計方針のため、実際に必要な権限は
サーバー管理者がロール設定で個別に付与する想定。/config でアクションを
有効化する時点、および実際に検知が発生してアクションを実行する時点の
両方でここを通し、権限が足りない場合は具体的にどの権限か明示する
（決定④）。
"""

from typing import Optional

import discord

ACTION_PERMISSION_LABELS = {
    "timeout": "メンバーをタイムアウト",
    "kick": "メンバーをキック",
    "ban": "メンバーをBAN",
    "delete": "メッセージの管理",
}

# discord.Permissionsの属性名との対応
_ACTION_PERMISSION_ATTR = {
    "timeout": "moderate_members",
    "kick": "kick_members",
    "ban": "ban_members",
    "delete": "manage_messages",
}


def missing_permission_label(
    guild: discord.Guild,
    action: str,
    channel: Optional[discord.abc.GuildChannel] = None,
) -> Optional[str]:
    """
    指定したactionの実行に必要な権限をBotが持っているか確認する。
    持っていれば None、足りなければ日本語ラベルを返す。

    delete（メッセージの管理）はチャンネルごとの権限上書きがあり得るため、
    channelが渡されていればchannel.permissions_for()で判定する。
    timeout/kick/banはギルド単位の権限なのでguild.me.guild_permissionsで判定する。
    """
    if action == "none":
        return None

    attr = _ACTION_PERMISSION_ATTR.get(action)
    if attr is None:
        return None

    me = guild.me
    if me is None:
        # メンバーキャッシュに載っていない稀なケース。安全側に倒して権限不足扱いにする。
        return ACTION_PERMISSION_LABELS.get(action, action)

    if action == "delete" and channel is not None:
        perms = channel.permissions_for(me)
    else:
        perms = me.guild_permissions

    if getattr(perms, attr, False):
        return None
    return ACTION_PERMISSION_LABELS[action]
