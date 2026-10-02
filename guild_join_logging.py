"""
guild_join_logging.py
Wardが新しいサーバーに導入された時／サーバーから削除された時、開発者用
チャンネルへ通知する。

検知ログ（detection_logging.py）とは別物 — こちらは「サーバーの中身」を
検知しているわけではなく、Discordの`on_guild_join`/`on_guild_remove`
イベントをそのまま開発者向けに通知するだけなので、専用ファイルに分けている。

GUILD_JOIN_LOG_CHANNEL_ID: 投稿先チャンネルID（開発者用、DEV_LOG_CHANNEL_IDと
同じ位置づけの単一の環境変数。サーバーごとの設定ではない）。導入・退出どちらも
同じチャンネルに投稿する。未設定なら投稿しない。

取りこぼし対策（reconcile_guilds）:
on_guild_join / on_guild_remove は、Botが停止・再起動している間に起きた導入/削除では
発火しない（起動時のサーバー一覧に最初から含まれるだけ）。そのため、DBの known_guilds
（把握済みサーバー）と起動時の client.guilds を突き合わせ、差分を導入/削除として通知する。
- 初回（known_guildsが空）は、現在の導入サーバーを一度だけ「棚卸し」として全件通知する。
- 削除は、guild.idが一覧に無いだけでは確定せず、fetch_guildで本当に抜けていることを確認する。

投稿内容にはユーザーが決められる文字列（サーバー名）が入るため、メンションは
一切許可しない（サーバー名が「@everyone」でも通知が飛ばないようにする）。
"""

import asyncio
import logging
import os
from typing import Optional

import discord

import database

logger = logging.getLogger(__name__)

GUILD_JOIN_LOG_CHANNEL_ID = os.getenv("GUILD_JOIN_LOG_CHANNEL_ID")

# 起動時の照合で一度に通知する上限（超過分は件数だけ通知する）
MAX_RECONCILE_LOGS = 25

_NO_MENTIONS = discord.AllowedMentions.none()


async def _get_log_channel(client: discord.Client):
    if not GUILD_JOIN_LOG_CHANNEL_ID:
        return None
    try:
        return client.get_channel(int(GUILD_JOIN_LOG_CHANNEL_ID)) or await client.fetch_channel(
            int(GUILD_JOIN_LOG_CHANNEL_ID)
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
        return None


def _owner_text(guild: discord.Guild) -> str:
    owner = guild.owner  # メンバーキャッシュに無ければNoneのことがある
    if owner is not None:
        return f"{owner.mention}（`{owner.id}`）"
    if guild.owner_id is not None:
        return f"`{guild.owner_id}`"
    return "不明"


async def _send(channel, view: discord.ui.LayoutView) -> None:
    try:
        await channel.send(view=view, allowed_mentions=_NO_MENTIONS)
    except (discord.Forbidden, discord.HTTPException):
        pass


def _build_view(title: str, colour: discord.Colour, lines: list[str]) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    container = discord.ui.Container(accent_color=colour)
    container.add_item(discord.ui.TextDisplay(title))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    view.add_item(container)
    return view


async def post_guild_join_log(
    client: discord.Client, guild: discord.Guild, note: Optional[str] = None
) -> None:
    channel = await _get_log_channel(client)
    if channel is None:
        return

    lines = [
        f"**サーバー名**: {guild.name or '不明'}",
        f"**サーバーID**: `{guild.id}`",
        f"**メンバー数**: {guild.member_count if guild.member_count is not None else '不明'}",
        f"**オーナー**: {_owner_text(guild)}",
    ]
    if guild.created_at is not None:
        lines.append(f"**サーバー作成日**: {discord.utils.format_dt(guild.created_at, 'D')}")
    if note:
        lines.append(f"**検出経路**: {note}")

    await _send(channel, _build_view("## 🆕 新規サーバーに導入されました", discord.Colour.green(), lines))


async def post_guild_leave_log(
    client: discord.Client, guild: discord.Guild, note: Optional[str] = None
) -> None:
    """
    導入解除（BANされた/追放された/管理者が削除した、いずれも同じイベント）時の通知。
    Botが既にサーバーから抜けた後の状態なので、member_count等はキャッシュ時点の
    古い値になっている可能性がある。
    """
    channel = await _get_log_channel(client)
    if channel is None:
        return

    lines = [
        f"**サーバー名**: {guild.name}",
        f"**サーバーID**: `{guild.id}`",
        f"**メンバー数（最終確認時点）**: {guild.member_count if guild.member_count is not None else '不明'}",
        f"**オーナー**: {_owner_text(guild)}",
    ]
    if note:
        lines.append(f"**検出経路**: {note}")

    await _send(channel, _build_view("## 👋 サーバーから削除されました", discord.Colour.red(), lines))


async def post_guild_leave_log_by_id(
    client: discord.Client, guild_id: str, name: Optional[str], note: Optional[str] = None
) -> None:
    """Guildオブジェクトが手元に無い削除（起動時の照合で検出したもの）用。保存してある名前だけ出す。"""
    channel = await _get_log_channel(client)
    if channel is None:
        return

    lines = [
        f"**サーバー名（最後に把握していたもの）**: {name or '不明'}",
        f"**サーバーID**: `{guild_id}`",
    ]
    if note:
        lines.append(f"**検出経路**: {note}")

    await _send(channel, _build_view("## 👋 サーバーから削除されました", discord.Colour.red(), lines))


async def _post_notice(client: discord.Client, text: str) -> None:
    channel = await _get_log_channel(client)
    if channel is None:
        return
    await _send(channel, _build_view("## ℹ️ サーバー一覧の照合", discord.Colour.light_grey(), [text]))


# ---------------------------------------------------------------------------
# known_guilds（把握済みサーバー）の更新。DB障害でイベント処理を止めないよう、例外は握る。
# ---------------------------------------------------------------------------


async def remember_guild(guild: discord.Guild) -> None:
    try:
        await asyncio.to_thread(database.upsert_known_guilds, [(str(guild.id), guild.name or "")])
    except Exception:
        logger.exception("known_guilds upsert failed: %s", guild.id)


async def forget_guild(guild_id: int) -> None:
    try:
        await asyncio.to_thread(database.remove_known_guilds, [str(guild_id)])
    except Exception:
        logger.exception("known_guilds delete failed: %s", guild_id)


async def _is_really_gone(client: discord.Client, guild_id: int) -> bool:
    """本当にBotがそのサーバーから抜けているか。判断できないときはFalse（次回に持ち越す）。"""
    try:
        await client.fetch_guild(guild_id)
    except (discord.NotFound, discord.Forbidden):
        return True
    except discord.HTTPException:
        return False
    return False


async def reconcile_guilds(client: discord.Client) -> None:
    """
    起動時（on_ready）に、known_guilds と現在の client.guilds を突き合わせる。
    - 把握していない現在のサーバー → 導入ログ（Bot停止中の導入を含む）
    - 把握しているが現在いないサーバー → 本当に抜けていれば削除ログ
    ログ投稿 → DB更新の順に行う（失敗時は、通知の取りこぼしより重複通知を選ぶ）。
    """
    try:
        known = await asyncio.to_thread(database.get_known_guilds)
    except Exception:
        logger.exception("reconcile: failed to read known_guilds")
        return

    current = {str(g.id): g for g in client.guilds}
    first_run = not known
    new_ids = [gid for gid in current if gid not in known]
    gone_candidates = [gid for gid in known if gid not in current]

    # 新規導入
    note = (
        "初回の棚卸し（現在の導入サーバーを一度だけ通知）"
        if first_run
        else "起動時の照合で検出（Bot停止中に導入された可能性）"
    )
    for gid in new_ids[:MAX_RECONCILE_LOGS]:
        await post_guild_join_log(client, current[gid], note=note)
    if len(new_ids) > MAX_RECONCILE_LOGS:
        await _post_notice(client, f"導入サーバーの通知は上限のため省略: 他 {len(new_ids) - MAX_RECONCILE_LOGS} 件")

    # 削除（本当に抜けているか確認してから）
    gone_ids = [gid for gid in gone_candidates if await _is_really_gone(client, int(gid))]
    for gid in gone_ids[:MAX_RECONCILE_LOGS]:
        await post_guild_leave_log_by_id(
            client, gid, known.get(gid), note="起動時の照合で検出（Bot停止中に削除された可能性）"
        )
    if len(gone_ids) > MAX_RECONCILE_LOGS:
        await _post_notice(client, f"削除サーバーの通知は上限のため省略: 他 {len(gone_ids) - MAX_RECONCILE_LOGS} 件")

    # DB更新（名前の変更も反映する）
    try:
        await asyncio.to_thread(
            database.upsert_known_guilds, [(gid, g.name or "") for gid, g in current.items()]
        )
        await asyncio.to_thread(database.remove_known_guilds, gone_ids)
    except Exception:
        logger.exception("reconcile: failed to update known_guilds")

    logger.info(
        "reconcile: current=%d known=%d new=%d removed=%d first_run=%s",
        len(current), len(known), len(new_ids), len(gone_ids), first_run,
    )
