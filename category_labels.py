"""
category_labels.py
xgomi-discord側 bot/commands/categories.py のカテゴリID→日本語ラベル
対応表の複製（表示専用）。プロジェクトを完全分離する方針のため複製している
— xgomi-discord側でカテゴリを追加・変更したら、ここも合わせて更新すること。
"""

USER_CATEGORY_LABELS = {
    "scam": "詐欺",
    "phishing": "フィッシング",
    "impersonation": "なりすまし",
    "raid-spam": "荒らし・スパム",
    "bad-solicitation": "悪質な勧誘",
    "harassment": "嫌がらせ",
    "doxxing": "個人情報の暴露",
    "hate-speech": "差別的言動",
    "bot-abuse": "bot悪用",
    "malicious-server-creator": "悪質サーバーの作成者",
    "malicious-bot-developer": "悪質Botの開発者",
    "other": "その他",
}

SERVER_CATEGORY_LABELS = {
    "scam-phishing": "詐欺・フィッシング勧誘",
    "illegal-tos-content": "違法・規約違反コンテンツ",
    "raid-hub": "荒らし・レイド拠点",
    "other": "その他",
}

BOT_CATEGORY_LABELS = {
    "malware-token-grabber": "トークン窃取・マルウェア",
    "raid-spam": "スパム・荒らし",
    "scam-phishing": "詐欺・フィッシング",
    "impersonation": "なりすまし",
    "data-harvesting": "無断データ収集・監視",
    "other": "その他",
}

LABELS_BY_TYPE = {
    "user": USER_CATEGORY_LABELS,
    "server": SERVER_CATEGORY_LABELS,
    "bot": BOT_CATEGORY_LABELS,
}


def label_for(category_id: str, target_type: str) -> str:
    return LABELS_BY_TYPE.get(target_type, {}).get(category_id, category_id)
