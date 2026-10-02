"""
database.py

report-utility-bot専用のNeon（PostgreSQL）プロジェクトに接続する。

方針転換により join_action / invite_action の選択式をやめ、
timeout_duration_minutes のみで挙動を制御する
（0 = タイムアウト無効化。メッセージ削除とログ投稿は常に継続）。

入室検知（ユーザー/Bot）機能は一旦オフのため、関連カラムは持たない。

known_guilds: Botが「導入済みと把握しているサーバー」の一覧。Bot停止中に導入/削除された
サーバーを、起動時に現在のサーバー一覧と突き合わせて検出するために使う
（on_guild_join / on_guild_remove は、Bot停止中のものは発火しないため）。
"""

import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

DEFAULT_TIMEOUT_MINUTES = 1440  # 24時間
MIN_TIMEOUT_MINUTES = 1
MAX_TIMEOUT_MINUTES = 40320  # 28日（Discordのtimeout仕様上の上限）
DISABLED_TIMEOUT_MINUTES = 0  # タイムアウトなし（削除・ログは継続）


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
            guild_id TEXT PRIMARY KEY,
            log_channel_id TEXT,
            timeout_duration_minutes INTEGER NOT NULL DEFAULT {DEFAULT_TIMEOUT_MINUTES},
            updated_at TEXT NOT NULL
        )"""
    )
    # 既存テーブルに対するマイグレーション
    _execute(
        f"ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS "
        f"timeout_duration_minutes INTEGER NOT NULL DEFAULT {DEFAULT_TIMEOUT_MINUTES}"
    )
    # join_action / invite_action の選択式は廃止（timeout_duration_minutesのみで制御）
    _execute("ALTER TABLE guild_settings DROP COLUMN IF EXISTS join_action")
    _execute("ALTER TABLE guild_settings DROP COLUMN IF EXISTS invite_action")
    _execute("ALTER TABLE guild_settings DROP COLUMN IF EXISTS timeout_duration_hours")

    _execute(
        """CREATE TABLE IF NOT EXISTS known_guilds (
            guild_id TEXT PRIMARY KEY,
            name TEXT,
            first_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )


def get_guild_settings(guild_id: str) -> dict:
    """
    設定行が無いサーバーは「未設定＝デフォルト（24時間timeout）」として扱う。
    まだ一度も設定コマンドを使っていないサーバーでも検知処理自体は動かせるように
    するため、行が無ければDBに書き込まずにデフォルト値の辞書だけを返す。
    """
    rows = _execute("SELECT * FROM guild_settings WHERE guild_id=%s", (guild_id,))
    if rows:
        return rows[0]
    return {
        "guild_id": guild_id,
        "log_channel_id": None,
        "timeout_duration_minutes": DEFAULT_TIMEOUT_MINUTES,
        "updated_at": None,
    }


def set_log_channel(guild_id: str, channel_id: Optional[str]) -> None:
    _upsert(guild_id, log_channel_id=channel_id)


def set_timeout_duration(guild_id: str, minutes: int) -> None:
    if minutes != DISABLED_TIMEOUT_MINUTES and not (MIN_TIMEOUT_MINUTES <= minutes <= MAX_TIMEOUT_MINUTES):
        raise ValueError(
            f"timeout minutes must be 0 (disabled) or between {MIN_TIMEOUT_MINUTES} and {MAX_TIMEOUT_MINUTES}"
        )
    _upsert(guild_id, timeout_duration_minutes=minutes)


def _upsert(guild_id: str, **fields) -> None:
    now = datetime.now(timezone.utc).isoformat()
    existing = get_guild_settings(guild_id)
    log_channel_id = fields.get("log_channel_id", existing["log_channel_id"])
    timeout_duration_minutes = fields.get(
        "timeout_duration_minutes", existing["timeout_duration_minutes"]
    )
    _execute(
        """
        INSERT INTO guild_settings (guild_id, log_channel_id, timeout_duration_minutes, updated_at)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (guild_id) DO UPDATE SET
            log_channel_id = EXCLUDED.log_channel_id,
            timeout_duration_minutes = EXCLUDED.timeout_duration_minutes,
            updated_at = EXCLUDED.updated_at
        """,
        (guild_id, log_channel_id, timeout_duration_minutes, now),
    )


# ---------------------------------------------------------------------------
# known_guilds（導入済みサーバーの把握）
# ---------------------------------------------------------------------------


def get_known_guilds() -> dict[str, Optional[str]]:
    """把握済みサーバーを {guild_id: サーバー名} で返す。"""
    rows = _execute("SELECT guild_id, name FROM known_guilds")
    return {r["guild_id"]: r["name"] for r in rows}


def upsert_known_guilds(guilds: list[tuple[str, str]]) -> None:
    """
    [(guild_id, name), ...] をまとめて登録/更新する（接続は1回だけ）。
    nameが空文字（Discord側の障害などで取得できなかった場合）のときは、
    既に保存してある名前を上書きしない。
    """
    if not guilds:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO known_guilds (guild_id, name, first_seen_at, updated_at)
                VALUES %s
                ON CONFLICT (guild_id) DO UPDATE SET
                    name = COALESCE(NULLIF(EXCLUDED.name, ''), known_guilds.name),
                    updated_at = EXCLUDED.updated_at
                """,
                [(gid, name, now, now) for gid, name in guilds],
            )
        conn.commit()
    finally:
        conn.close()


def remove_known_guilds(guild_ids: list[str]) -> None:
    if not guild_ids:
        return
    _execute("DELETE FROM known_guilds WHERE guild_id = ANY(%s)", (list(guild_ids),))
