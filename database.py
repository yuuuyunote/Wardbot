"""
database.py
report-utility-bot専用のNeon（PostgreSQL）プロジェクトに接続する。
xgomi-discord・Guide Base +のダッシュボード用DBとは完全に別プロジェクト
（設計メモ通り、責務・障害範囲を分離するため）。

テーブルはguild_settingsの1つだけ。検知ログはDBに保存せず、各サーバーの
ログチャンネル＋開発者用横断チャンネルへのリアルタイム投稿のみで完結させる
という設計判断のため、detection_logs系のテーブルは持たない。

timeout_duration_hours: サーバーごとにtimeout時間を設定できるようにした列。
初期値は24時間。上限672時間（28日）はDiscordのtimeout仕様上の最大値。
"""

import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

VALID_JOIN_ACTIONS = frozenset({"none", "timeout", "kick", "ban"})
VALID_INVITE_ACTIONS = frozenset({"none", "delete", "timeout", "kick", "ban"})
DEFAULT_TIMEOUT_HOURS = 24
MIN_TIMEOUT_HOURS = 1
MAX_TIMEOUT_HOURS = 672  # Discordのtimeout上限（28日）


def get_conn():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise ValueError("DATABASE_URL が設定されていません")
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def _execute(sql: str, args: tuple = ()) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            conn.commit()
            try:
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            except psycopg2.ProgrammingError:
                return []
    finally:
        conn.close()


def init_db() -> None:
    _execute(
        f"""CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id              TEXT PRIMARY KEY,
            join_action           TEXT NOT NULL DEFAULT 'none',
            invite_action         TEXT NOT NULL DEFAULT 'none',
            log_channel_id        TEXT,
            timeout_duration_hours INTEGER NOT NULL DEFAULT {DEFAULT_TIMEOUT_HOURS},
            updated_at            TEXT NOT NULL
        )"""
    )
    # 既存テーブルに対するマイグレーション（timeout_duration_hours追加分）
    _execute(
        f"ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS "
        f"timeout_duration_hours INTEGER NOT NULL DEFAULT {DEFAULT_TIMEOUT_HOURS}"
    )


def get_guild_settings(guild_id: str) -> dict:
    """
    設定行が無いサーバーは「未設定＝全部デフォルト」として扱う。
    まだ一度も/configされていないサーバーでも検知処理自体は動かせるようにするため、
    行が無ければDBに書き込まずにデフォルト値の辞書だけを返す（無駄なINSERTをしない）。
    """
    rows = _execute("SELECT * FROM guild_settings WHERE guild_id=%s", (guild_id,))
    if rows:
        return rows[0]
    return {
        "guild_id": guild_id,
        "join_action": "none",
        "invite_action": "none",
        "log_channel_id": None,
        "timeout_duration_hours": DEFAULT_TIMEOUT_HOURS,
        "updated_at": None,
    }


def set_join_action(guild_id: str, action: str) -> None:
    if action not in VALID_JOIN_ACTIONS:
        raise ValueError(f"invalid join_action: {action}")
    _upsert(guild_id, join_action=action)


def set_invite_action(guild_id: str, action: str) -> None:
    if action not in VALID_INVITE_ACTIONS:
        raise ValueError(f"invalid invite_action: {action}")
    _upsert(guild_id, invite_action=action)


def set_log_channel(guild_id: str, channel_id: Optional[str]) -> None:
    _upsert(guild_id, log_channel_id=channel_id)


def set_timeout_duration(guild_id: str, hours: int) -> None:
    if not (MIN_TIMEOUT_HOURS <= hours <= MAX_TIMEOUT_HOURS):
        raise ValueError(f"timeout hours must be between {MIN_TIMEOUT_HOURS} and {MAX_TIMEOUT_HOURS}")
    _upsert(guild_id, timeout_duration_hours=hours)


def _upsert(guild_id: str, **fields) -> None:
    """
    guild_settingsの部分更新。行が無ければ他のカラムはデフォルト値でINSERTし、
    指定されたフィールドだけ上書きする。
    """
    now = datetime.now(timezone.utc).isoformat()
    existing = get_guild_settings(guild_id)

    join_action = fields.get("join_action", existing["join_action"])
    invite_action = fields.get("invite_action", existing["invite_action"])
    log_channel_id = fields.get("log_channel_id", existing["log_channel_id"])
    timeout_duration_hours = fields.get("timeout_duration_hours", existing["timeout_duration_hours"])

    _execute(
        """
        INSERT INTO guild_settings
            (guild_id, join_action, invite_action, log_channel_id, timeout_duration_hours, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (guild_id) DO UPDATE SET
            join_action = EXCLUDED.join_action,
            invite_action = EXCLUDED.invite_action,
            log_channel_id = EXCLUDED.log_channel_id,
            timeout_duration_hours = EXCLUDED.timeout_duration_hours,
            updated_at = EXCLUDED.updated_at
        """,
        (guild_id, join_action, invite_action, log_channel_id, timeout_duration_hours, now),
    )
