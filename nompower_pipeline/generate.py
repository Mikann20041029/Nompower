# nompower_pipeline/generate.py
from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from slugify import slugify
import json

from .util import (
    ROOT,
    read_text,
    write_text,
    read_json,
    write_json,
    normalize_url,
    simple_tokens,
    jaccard,
    sanitize_llm_html,
)
from .deepseek import DeepSeekClient
from .reddit import fetch_rss_entries
from .render import env_for, render_to_file, write_asset

CONFIG_PATH = ROOT / "nompower_pipeline" / "config.json"
PROCESSED_PATH = ROOT / "processed_urls.txt"
ARTICLES_PATH = ROOT / "data" / "articles.json"
LAST_RUN_PATH = ROOT / "data" / "last_run.json"
SITE_DIR = ROOT / "site"

TEMPLATES_DIR = ROOT / "nompower_pipeline" / "templates"
STATIC_DIR = ROOT / "nompower_pipeline" / "static"

ADS_TOP = """<script src="https://pl28593834.effectivegatecpm.com/bf/0c/41/bf0c417e61a02af02bb4fab871651c1b.js"></script>"""
ADS_MID = """<script src="https://quge5.com/88/tag.min.js" data-zone="206389" async data-cfasync="false"></script>"""
ADS_BOTTOM = """<script type="text/javascript">
var infolinks_pid = 3443178;
var infolinks_wsid = 0;
</script>
<script type="text/javascript" src="https://resources.infolinks.com/js/infolinks_main.js"></script>"""

FIXED_POLICY_BLOCK = """
<p><strong>Policy & Transparency (to stay search-friendly)</strong></p>
<ul>
  <li><strong>Source & attribution:</strong> Each post is based on a public Reddit RSS item. We always link to the original Reddit post and do not claim ownership of third-party content.</li>
  <li><strong>Original value:</strong> We add commentary, context, and takeaways. If something is uncertain, we label it as speculation rather than stating it as fact.</li>
  <li><strong>No manipulation:</strong> No cloaking, hidden text, doorway pages, or misleading metadata. Titles and summaries reflect the on-page content.</li>
  <li><strong>Safety filters:</strong> We skip obvious adult/self-harm/gore keywords and avoid NSFW feeds.</li>
  <li><strong>Ads:</strong> Third-party scripts may show ads we do not directly control. If you see problematic ads, contact us and we will adjust providers/placement.</li>
  <li><strong>Removal requests:</strong> If you believe content should be removed (copyright, personal data, etc.), email us with the URL and justification.</li>
</ul>
<p>Contact: <a href="mailto:{contact_email}">{contact_email}</a></p>
""".strip()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_processed() -> set[str]:
    s = read_text(PROCESSED_PATH)
    lines = [normalize_url(x) for x in s.splitlines() if x.strip()]
    return set(lines)


def append_processed(url: str) -> None:
    url = normalize_url(url)
    existing = load_processed()
    if url in existing:
        return

    current = read_text(PROCESSED_PATH).rstrip()
    if current.strip():
        current += "\n"
    current += url + "\n"
    write_text(PROCESSED_PATH, current)


def is_blocked(title: str, blocked_kw: list[str]) -> bool:
    t = (title or "").lower()
    for kw in blocked_kw:
        if kw.lower() in t:
            return True
    return False


def pick_candidate(cfg: dict, processed: set[str], articles: list[dict]) -> dict | None:
    blocked_kw = cfg["safety"]["blocked_keywords"]

    prev_titles = [a.get("title", "") for a in articles]
    prev_tok = [simple_tokens(t) for t in prev_titles if t]

    candidates: list[dict] = []
    for rss in cfg["feeds"]["reddit_rss"]:
        for e in fetch_rss_entries(rss):
            link = normalize_url(e["link"])
            if not link or link in processed:
                continue

            if is_blocked(e["title"], blocked_kw):
                continue

            tok = simple_tokens(e["title"])
            too_similar = any(jaccard(tok, pt) >= 0.78 for pt in prev_tok)
            if too_similar:
                continue

            # ✅ RSSから拾った安全な画像だけ使う（i.redd.itのみ）
            e["image_url"] = e.get("hero_image", "") or ""
            e["image_kind"] = e.get("hero_image_kind", "none") or "none"

            # スコア/コメントが取れないので、RSS単体は順序を保つ（先頭がトレンドの想定）
            candidates.append(e)

    return candidates[0] if candidates else None


def deepseek_article(cfg: dict, item: dict) -> str:
    ds = DeepSeekClient()
    model = cfg["generation"]["model"]
    target_words = int(cfg["generation"]["target_words"])
    temp = float(cfg["generation"]["temperature"])

    title = item["title"]
    link = item["link"]
    summary = item.get("summary", "")

    system = (
        "You are an editorial writer for a tech/news digest site. "
        "Write in English only. Do not fabricate facts. If uncertain, label it clearly as speculation. "
        "Be energetic and slightly hyped, but keep it accurate and non-defamatory. "
        "Avoid copyrighted copying; paraphrase and add original commentary and takeaways. "
        "No adult content, hate, or self-harm content."
    )

    user = f"""
Write an original article (HTML body only; use <p>, <h2>, <ul><li>) based on this Reddit post.

Post title: {title}
Permalink: {link}
RSS summary snippet (may be partial): {summary}

Requirements:
- Target length: ~{target_words} words (roughly).
- Structure:
  1) Hook (1 short paragraph)
  2) What happened (2-3 paragraphs)
  3) Why people care (2-3 paragraphs)
  4) Practical takeaways (bullet list)
  5) "Source" line linking to the Reddit permalink
- Style: slightly exaggerated / future-facing tone, but NEVER invent numbers, quotes, or events.
- If the topic implies missing details, explicitly say what's unknown and what would confirm it.
- Keep it safe for general audiences.
""".strip()

    out = ds.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temp,
        max_tokens=2400,
    )
    return sanitize_llm_html(out)


def compute_rankings(articles: list[dict]) -> list[dict]:
    # RSS-only mode: use recency as ranking
    return sorted(articles, key=lambda a: a.get("published_ts", ""), reverse=True)


def related_articles(current: dict, articles: list[dict], k: int = 6) -> list[dict]:
    cur_tok = simple_tokens(current.get("title", ""))
    scored: list[tuple[float, dict]] = []
    for a in articles:
        if a.get("id") == current.get("id"):
            continue
        sim = jaccard(cur_tok, simple_tokens(a.get("title", "")))
        scored.append((sim, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for s, a in scored[:k] if s > 0.05]


def build_site(cfg: dict, articles: list[dict]) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "articles").mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "assets").mkdir(parents=True, exist_ok=True)

    write_asset(SITE_DIR / "assets" / "style.css", STATIC_DIR / "style.css")
    write_asset(SITE_DIR / "assets" / "fx.js", STATIC_DIR / "fx.js")

    base_url = cfg["site"]["base_url"].rstrip("/")
    robots = f"""User-agent: *
Allow: /

Sitemap: {base_url}/sitemap.xml
"""
    (SITE_DIR / "robots.txt").write_text(robots, encoding="utf-8")

    urls = [f"{base_url}/"] + [f"{base_url}{a['path']}" for a in articles]
    sitemap_items = "\n".join([f"<url><loc>{u}</loc></url>" for u in urls])
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{sitemap_items}
</urlset>
"""
    (SITE_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    jenv = env_for(TEMPLATES_DIR)

    ranking = compute_rankings(articles)[:10]
    new_articles = sorted(articles, key=lambda a: a.get("published_ts", ""), reverse=True)[:10]

    render_to_file(
        jenv,
        "index.html",
        {
            "site": cfg["site"],
            "ranking": ranking,
            "new_articles": new_articles,
            "ads_top": ADS_TOP,
            "ads_mid": ADS_MID,
            "ads_bottom": ADS_BOTTOM,
            "now_iso": now_utc_iso(),
        },
        SITE_DIR / "index.html",
    )

    static_pages = [
        ("about", "About Nompower", "<p>Nompower is a daily digest that curates a single noteworthy Reddit item and adds commentary, context, and takeaways.</p>"),
        ("privacy", "Privacy", "<p>We do not require accounts. Third-party ad scripts may set cookies or collect device identifiers. See each provider’s policy. If you want removal or have concerns, contact us.</p>"),
        ("terms", "Terms", "<p>Use at your own risk. Content is informational and may be incomplete. We link to sources and welcome corrections.</p>"),
        ("disclaimer", "Disclaimer", "<p>This site is not affiliated with Reddit. Trademarks belong to their owners. We do not guarantee accuracy, availability, or outcomes.</p>"),
        ("contact", "Contact", f"<p>Email: <a href='mailto:{cfg['site']['contact_email']}'>{cfg['site']['contact_email']}</a></p>"),
    ]

    for slug, title, body in static_pages:
        render_to_file(
            jenv,
            "static.html",
            {
                "site": cfg["site"],
                "page_title": title,
                "page_body": body,
                "ads_top": ADS_TOP,
                "ads_mid": ADS_MID,
                "ads_bottom": ADS_BOTTOM,
                "now_iso": now_utc_iso(),
            },
            SITE_DIR / f"{slug}.html",
        )

    for a in articles:
        rel = related_articles(a, articles, k=6)
        render_to_file(
            jenv,
            "article.html",
            {
                "site": cfg["site"],
                "a": a,
                "related": rel,
                "ranking": ranking,
                "new_articles": new_articles,
                "policy_block": FIXED_POLICY_BLOCK.format(contact_email=cfg["site"]["contact_email"]),
                "ads_top": ADS_TOP,
                "ads_mid": ADS_MID,
                "ads_bottom": ADS_BOTTOM,
                "now_iso": now_utc_iso(),
            },
            SITE_DIR / a["path"].lstrip("/"),
        )


def write_last_run(cfg: dict, payload: dict[str, Any]) -> None:
    base_url = cfg["site"]["base_url"].rstrip("/")
    out = {
        "updated_utc": now_utc_iso(),
        "homepage_url": base_url + "/",
        **payload,
    }
    write_json(LAST_RUN_PATH, out)


def main() -> None:
    cfg = load_config()
    base_url = cfg["site"]["base_url"].rstrip("/")

    processed = load_processed()
    articles = read_json(ARTICLES_PATH, default=[])

    cand = pick_candidate(cfg, processed, articles)
    if not cand:
        build_site(cfg, articles)
        write_last_run(
            cfg,
            {
                "created": False,
                "article_url": "",
                "article_title": "",
                "source_url": "",
                "note": "No new candidate found. Site rebuilt.",
            },
        )
        return

    body_html = deepseek_article(cfg, cand)

    ts = datetime.now(timezone.utc)
    ymd = ts.strftime("%Y-%m-%d")
    slug = slugify(cand["title"])[:80] or f"post-{int(ts.timestamp())}"
    path = f"/articles/{ymd}-{slug}.html"
    article_url = base_url + path

    entry = {
        "id": f"{ymd}-{slug}",
        "title": cand["title"],
        "path": path,
        "published_ts": ts.isoformat(timespec="seconds"),
        "source_url": cand["link"],
        "rss": cand.get("rss", ""),
        "summary": cand.get("summary", ""),
        "body_html": body_html,
        # ✅ RSSから拾った安全画像（i.redd.itのみ）。無ければ空で表示されない
        "hero_image": cand.get("image_url", "") or "",
        "hero_image_kind": cand.get("image_kind", "none") or "none",
    }

    append_processed(cand["link"])
    articles.insert(0, entry)
    write_json(ARTICLES_PATH, articles)

    build_site(cfg, articles)

    write_last_run(
        cfg,
        {
            "created": True,
            "article_url": article_url,
            "article_path": path,
            "article_title": cand["title"],
            "source_url": cand["link"],
        },
    )


if __name__ == "__main__":
    main()
