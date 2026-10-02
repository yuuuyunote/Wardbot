"""
main.py

report-utility-bot のエントリーポイント。

必要なIntent（Discord Developer PortalでのPrivileged Gateway Intents有効化も
必須）:
- members: on_member_join（入室検知）に必須
- message_content: on_message本文からの招待/掲示板リンク検知に必須

重要: load_dotenv()は他のプロジェクト内モジュールをimportするより前に呼ぶこと
（blocklist_data.py等の順序バグを踏まえた対応）。
"""

from dotenv import load_dotenv

load_dotenv()

import os

import discord
from discord import app_commands

import database
from commands import setup_commands
from events import setup_events
from guild_join_logging import reconcile_guilds

GUILD_ID = os.getenv("GUILD_ID")


def main() -> None:
    database.init_db()

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True

    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    setup_commands(tree)
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

        # Bot停止中に導入/削除されたサーバーを、known_guildsと突き合わせて通知する。
        # on_readyは再接続のたびに呼ばれるが、照合は冪等（2回目以降は差分が出ない）。
        try:
            await reconcile_guilds(client)
        except Exception as e:  # 起動処理は止めない
            print(f"[reconcile] failed: {e!r}")

    token = os.environ["DISCORD_BOT_TOKEN"]
    client.run(token)


if __name__ == "__main__":
    main()
