"""
blocklist_data.py
xgomi-discordリポジトリの dist/{users,servers,bots}.json を取得・キャッシュする。
report-utility-bot側はこのキャッシュだけを見て、入室検知・招待/掲示板リンク検知の
突合を行う。書き込み（/report相当）はここでは行わない — 通報データの生成・承認は
xgomi-discord側のBotの役割で、こちらは公開データの消費専用。

BLOCKLIST_DATA_REPO / BLOCKLIST_DATA_BRANCH は関数内で毎回os.getenv()する
（モジュールのトップレベルで1回だけ読む実装にしていたところ、
load_dotenv()の呼び出し順序次第で空文字のまま固定されてしまう障害が
実際に発生したため、呼び出しごとに読み直す形に直した）。
"""

import os
import time
from typing import Optional

import aiohttp

CACHE_TTL_SECONDS = 60


def _data_repo() -> str:
    return os.getenv("BLOCKLIST_DATA_REPO", "")


def _data_branch() -> str:
    return os.getenv("BLOCKLIST_DATA_BRANCH", "main")


class BlocklistFetchError(Exception):
    pass


class BlocklistCache:
    def __init__(self, dist_filename: str) -> None:
        self._dist_filename = dist_filename
        self._data: Optional[list] = None
        self._fetched_at: float = 0.0

    async def get(self, force_refresh: bool = False) -> list:
        data_repo = _data_repo()
        if not data_repo:
            raise BlocklistFetchError("BLOCKLIST_DATA_REPO が設定されていません。")

        now = time.monotonic()
        if not force_refresh and self._data is not None and (now - self._fetched_at) < CACHE_TTL_SECONDS:
            return self._data

        url = (
            f"https://raw.githubusercontent.com/{data_repo}/{_data_branch()}/dist/{self._dist_filename}"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200:
                    raise BlocklistFetchError(f"dist/{self._dist_filename} の取得に失敗しました（status: {res.status}）")
                data = await res.json(content_type=None)

        self._data = data
        self._fetched_at = now
        return data

    async def find(self, target_id: str, force_refresh: bool = False) -> Optional[dict]:
        data = await self.get(force_refresh=force_refresh)
        for entry in data:
            if entry.get("id") == target_id:
                return entry
        return None


user_blocklist_cache = BlocklistCache("users.json")
server_blocklist_cache = BlocklistCache("servers.json")
bot_blocklist_cache = BlocklistCache("bots.json")

BLOCKLIST_CACHES_BY_TYPE: dict[str, BlocklistCache] = {
    "user": user_blocklist_cache,
    "server": server_blocklist_cache,
    "bot": bot_blocklist_cache,
}


def cache_for(target_type: str) -> BlocklistCache:
    cache = BLOCKLIST_CACHES_BY_TYPE.get(target_type)
    if cache is None:
        raise BlocklistFetchError(f"unknown target_type: {target_type}")
    return cache
