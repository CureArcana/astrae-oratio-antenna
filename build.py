#!/usr/bin/env python3
"""
astrae-oratio.com アンテナサイト ビルドスクリプト

複数のRSSフィードを取得し、新着順にマージして静的HTMLを生成する。
GitHub Actions で定期実行 → public/ に出力 → Cloudflare Pages が配信。

作者: ばぶちゃん（with コッコロ・マリン・シェフィールド）
"""

from __future__ import annotations

import datetime as dt
import html
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import feedparser
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ============================================================
# 設定：取得するRSSソース
# ============================================================
# 試運転は asuora.com のみ。後でソース追加するときはここに足すだけ。
FEEDS: list[dict] = [
    {
        "name": "アスオラまとめ速報",
        "url": "https://asuora.com/feed/",
        "site_url": "https://asuora.com/",
    },
    # 例：将来追加する場合
    # {"name": "他サイト名", "url": "https://example.com/feed/", "site_url": "https://example.com/"},
]

MAX_ENTRIES = 100  # 一覧に表示する記事数の上限
TIMEOUT_SECONDS = 30
USER_AGENT = "astrae-oratio-antenna/1.0 (+https://astrae-oratio.com)"

ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "public"


@dataclass
class Entry:
    """1記事ぶんのエントリ。"""

    source_name: str
    source_url: str
    title: str
    link: str
    published: dt.datetime
    summary: str

    @property
    def published_jst_str(self) -> str:
        jst = self.published.astimezone(dt.timezone(dt.timedelta(hours=9)))
        return jst.strftime("%Y-%m-%d %H:%M")

    @property
    def published_iso(self) -> str:
        return self.published.astimezone(dt.timezone.utc).isoformat()


def parse_published(raw_entry) -> dt.datetime:
    """feedparser のエントリから datetime を取り出す。なければ now。"""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(raw_entry, key, None) or raw_entry.get(key)
        if t:
            try:
                return dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
            except (TypeError, ValueError):
                continue
    return dt.datetime.now(tz=dt.timezone.utc)


def clean_summary(raw_summary: str | None, limit: int = 140) -> str:
    """summary からHTMLを軽く落として短縮。"""
    if not raw_summary:
        return ""
    import re
    text = re.sub(r"<[^>]+>", "", raw_summary)
    text = html.unescape(text).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def fetch_feed(feed_def: dict) -> list[Entry]:
    """1つのRSSをfetchしてEntryリスト化。"""
    print(f"[fetch] {feed_def['name']} <- {feed_def['url']}", file=sys.stderr)
    parsed = feedparser.parse(
        feed_def["url"],
        agent=USER_AGENT,
        request_headers={"Cache-Control": "no-cache"},
    )
    if parsed.bozo and not parsed.entries:
        print(f"  [warn] parse error: {parsed.bozo_exception}", file=sys.stderr)
        return []

    entries: list[Entry] = []
    for raw in parsed.entries:
        link = raw.get("link", "")
        title = (raw.get("title") or "(無題)").strip()
        if not link:
            continue
        entries.append(
            Entry(
                source_name=feed_def["name"],
                source_url=feed_def["site_url"],
                title=title,
                link=link,
                published=parse_published(raw),
                summary=clean_summary(raw.get("summary") or raw.get("description")),
            )
        )
    print(f"  [ok] {len(entries)} entries", file=sys.stderr)
    return entries


def render_site(entries: list[Entry]) -> None:
    """テンプレートからHTML出力。"""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now_jst = dt.datetime.now(tz=dt.timezone(dt.timedelta(hours=9)))
    ctx = {
        "entries": entries,
        "feeds": FEEDS,
        "generated_at": now_jst.strftime("%Y-%m-%d %H:%M JST"),
        "generated_at_iso": now_jst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "generated_at_date": now_jst.strftime("%Y-%m-%d"),
        "site_title": "アストラエ・オラティオ まとめサイトアンテナ！",
        "site_url": "https://astrae-oratio.com",
        "main_blog_url": "https://asuora.com",
        "web3forms_key": "a345584b-327b-486b-8311-f553c247a3e6",
    }

    # index.html
    index_tpl = env.get_template("index.html.j2")
    (OUTPUT_DIR / "index.html").write_text(index_tpl.render(**ctx), encoding="utf-8")
    print(f"[write] {OUTPUT_DIR / 'index.html'}", file=sys.stderr)

    # robots.txt
    (OUTPUT_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://astrae-oratio.com/sitemap.xml\n",
        encoding="utf-8",
    )

    # sitemap.xml（簡易）
    sitemap_tpl = env.get_template("sitemap.xml.j2")
    (OUTPUT_DIR / "sitemap.xml").write_text(sitemap_tpl.render(**ctx), encoding="utf-8")

    # feed.xml（アンテナ自身のRSS）
    feed_tpl = env.get_template("feed.xml.j2")
    (OUTPUT_DIR / "feed.xml").write_text(feed_tpl.render(**ctx), encoding="utf-8")

    # /contact/index.html（お問い合わせフォーム）
    contact_tpl = env.get_template("contact.html.j2")
    contact_dir = OUTPUT_DIR / "contact"
    contact_dir.mkdir(parents=True, exist_ok=True)
    (contact_dir / "index.html").write_text(contact_tpl.render(**ctx), encoding="utf-8")
    print(f"[write] {contact_dir / 'index.html'}", file=sys.stderr)

    # /thanks/index.html（送信完了ページ）
    thanks_tpl = env.get_template("thanks.html.j2")
    thanks_dir = OUTPUT_DIR / "thanks"
    thanks_dir.mkdir(parents=True, exist_ok=True)
    (thanks_dir / "index.html").write_text(thanks_tpl.render(**ctx), encoding="utf-8")
    print(f"[write] {thanks_dir / 'index.html'}", file=sys.stderr)


def main() -> int:
    all_entries: list[Entry] = []
    for f in FEEDS:
        all_entries.extend(fetch_feed(f))

    # 新着順
    all_entries.sort(key=lambda e: e.published, reverse=True)
    all_entries = all_entries[:MAX_ENTRIES]

    if not all_entries:
        print("[error] no entries fetched", file=sys.stderr)
        # 失敗時もトップページは出す（前回ビルドが残っていればそれが残る）
        return 1

    render_site(all_entries)
    print(f"[done] generated {len(all_entries)} entries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
