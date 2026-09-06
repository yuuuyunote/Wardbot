"""
main.py
report-utility-bot のエントリーポイント。

必要なIntent（Discord Developer PortalでのPrivileged Gateway Intents有効化も
必須）:
- members: on_member_join（入室検知）に必須
- message_content: on_message本文からの招待/掲示板リンク検知に必須

Bot招待URLの権限ビットは最小権限方針（決定①）。timeout/kick/ban/
メッセージの管理は、各サーバーの管理者が/configでアクションを有効化した後、
サーバー設定でBotのロールに個別付与してもらう運用。

重要: load_dotenv()は他のプロジェクト内モジュールをimportするより前に
呼ぶこと。blocklist_data.py等、モジュールのトップレベルでos.getenv()を
呼んでいるファイルがあるため、load_dotenv()が後だと.envの内容が
反映される前に空文字で確定してしまう（実際にこの順序バグでBLOCKLIST_DATA_REPO
が空になる障害が発生した）。
"""

from dotenv import load_dotenv

load_dotenv()

import os

import discord
from discord import app_commands

import database
from config import ConfigGroup
from events import setup_events

# 開発中の即時sync用。本番運用ではGUILD_IDを設定せずグローバルsyncにする
# （xgomi-discord側のBotと同じ運用方針）。
GUILD_ID = os.getenv("GUILD_ID")


def main() -> None:
    database.init_db()

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True

    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    tree.add_command(ConfigGroup())

    setup_events(client)

    @client.event
    async def on_ready() -> None:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
            print(f"[commands] synced {len(synced)} command(s) to guild {GUILD_ID}")
        else:
            synced = await tree.sync()
            print(f"[commands] synced {len(synced)} command(s) globally")
        print(f"[ready] logged in as {client.user} ({len(client.guilds)} guild(s))")

    token = os.environ["DISCORD_BOT_TOKEN"]
    client.run(token)


if __name__ == "__main__":
    main()
