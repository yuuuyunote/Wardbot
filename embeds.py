"""
embeds.py
コマンド応答用の埋め込み（Embed）を統一デザインで作るヘルパー。

検知ログ側（detection_logging.py, Components V2）とは別に、インタラクティブな
設定コマンドの応答はEmbedで統一する（シンプルな確認メッセージなのでEmbedで
十分、かつComponents V2は同一メッセージ内でEmbedと併用できないため使い分ける）。

info_embedの色はGuide Base +系プロジェクトのアンバーアクセント（#E8A13E、
ダークモード基準）に寄せて、ブランドの一貫性を持たせている。
"""

import discord

BRAND_COLOR = discord.Colour.from_str("#E8A13E")


def success_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=description, colour=discord.Colour.green())


def warning_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"⚠️ {title}", description=description, colour=discord.Colour.orange())


def error_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"❌ {title}", description=description, colour=discord.Colour.red())


def info_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, colour=BRAND_COLOR)
