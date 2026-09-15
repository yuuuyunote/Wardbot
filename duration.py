"""
duration.py
"10m" / "2h" / "3d" のような単位付き文字列、または無効化を表す"0"を
timeoutの分数に変換する。
"""

import re

_PATTERN = re.compile(r"^(\d+)\s*(m|h|d)$", re.IGNORECASE)
_UNIT_TO_MINUTES = {"m": 1, "h": 60, "d": 60 * 24}


def parse_duration_to_minutes(text: str) -> int:
    """
    "10m"→10, "2h"→120, "3d"→4320、"0"→0（無効化＝ログのみ）に変換する。
    形式が不正ならValueErrorを投げる（呼び出し側でユーザーへのエラー表示に使う）。
    """
    text = text.strip()
    if text == "0":
        return 0

    m = _PATTERN.match(text)
    if not m:
        raise ValueError(
            f"「{text}」は認識できない形式です。数字 + m/h/d の形式（例: 10m, 2h, 3d）、"
            "または無効化する場合は「0」を入力してください。"
        )
    value, unit = m.groups()
    return int(value) * _UNIT_TO_MINUTES[unit.lower()]


def format_minutes(total_minutes: int) -> str:
    """分数を人間に読みやすい表記に戻す（設定確認画面などで使う）。"""
    if total_minutes == 0:
        return "無効（ログのみ、タイムアウトなし）"
    if total_minutes % (60 * 24) == 0:
        return f"{total_minutes // (60 * 24)}d"
    if total_minutes % 60 == 0:
        return f"{total_minutes // 60}h"
    return f"{total_minutes}m"