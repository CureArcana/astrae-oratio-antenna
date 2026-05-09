# astrae-oratio.com アンテナサイト

アストラエ・オラティオ（アスオラ）関連まとめ記事のRSSアンテナサイト。

## 構成

- **ホスティング:** Cloudflare Pages（無料）
- **ビルド:** GitHub Actions（6時間ごとスケジュール実行）
- **生成:** Python（feedparser + Jinja2）
- **公開先:** https://astrae-oratio.com

## ローカルでビルド

```bash
pip install -r requirements.txt
python build.py
# public/index.html が生成される
```

## RSSソース追加

`build.py` の `FEEDS` リストに辞書を追加するだけ。

```python
FEEDS = [
    {"name": "サイト名", "url": "https://example.com/feed/", "site_url": "https://example.com/"},
]
```

## デプロイフロー

1. GitHub Actions がスケジュール実行（cron: 03/09/15/21 JST）
2. `python build.py` で `public/` 配下を再生成
3. 変更があれば自動 commit & push
4. Cloudflare Pages が push を検知して自動デプロイ

`workflow_dispatch` で手動実行も可能。
