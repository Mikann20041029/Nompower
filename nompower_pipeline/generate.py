# nompower_pipeline/generate.py
from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from slugify import slugify
import json
import re
import html as _html

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

# === Ads (strings must be standalone and syntactically valid) ===
ADS_TOP = """<script src="https://pl28593834.effectivegatecpm.com/bf/0c/41/bf0c417e61a02af02bb4fab871651c1b.js"></script>"""
ADS_MID = """<script src="https://quge5.com/88/tag.min.js" data-zone="206389" async data-cfasync="false"></script>"""
ADS_BOTTOM = """<script type="text/javascript"></script>"""  # keep simple; replace with your actual bottom ad if needed

ads_rail_left = """
<script src="https://pl28593834.effectivegatecpm.com/bf/0c/41/bf0c417e61a02af02bb4fab871651c1b.js"></script>
""".strip()

ads_rail_right = """
<script src="https://quge5.com/88/tag.min.js" data-zone="206389" async data-cfasync="false"></script>
""".strip()

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
IMPORTANT:
- Do NOT repeat the post title in the body.
- Do NOT output <h1> under any circumstances.
- Do NOT restate the title as a paragraph.
- Start directly with a short hook paragraph (<p>).
- Use <h2> for section headings only.

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


def strip_leading_duplicate_title(body_html: str, title: str) -> str:
    """
    Remove duplicated title that LLM sometimes outputs at the beginning of body_html.
    We keep the template H1 (a.title) as the single source of truth.

    Removes if the first:
    - <h1> equals title
    - <h2> equals title
    - <p> equals title
    - plain text line equals title (rare)
    """
    if not body_html or not title:
        return body_html

    # Normalize title for comparison
    t = _html.unescape(title).strip()
    t_norm = re.sub(r"\s+", " ", t).lower()

    def _same(text: str) -> bool:
        x = _html.unescape(text or "").strip()
        x = re.sub(r"\s+", " ", x).lower()
        return x == t_norm

    s = body_html.lstrip()

    # 1) remove leading <h1>...</h1> if it matches title
    m = re.match(r"(?is)^\s*<h1[^>]*>(.*?)</h1>\s*", s)
    if m and _same(m.group(1)):
        return s[m.end() :].lstrip()

    # 2) remove leading <h2>...</h2> if it matches title
    m = re.match(r"(?is)^\s*<h2[^>]*>(.*?)</h2>\s*", s)
    if m and _same(m.group(1)):
        return s[m.end() :].lstrip()

    # 3) remove leading <p>...</p> if it matches title
    m = re.match(r"(?is)^\s*<p[^>]*>(.*?)</p>\s*", s)
    if m:
        inner = re.sub(r"(?is)<[^>]+>", "", m.group(1))
        if _same(inner):
            return s[m.end() :].lstrip()

    # 4) remove leading plain-text title line (defensive)
    m = re.match(r"(?is)^\s*([^<\n]{10,200})\s*(?:<br\s*/?>|\n)\s*", s)
    if m and _same(m.group(1)):
        return s[m.end() :].lstrip()

    return body_html


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


def write_rss_feed(cfg: dict, articles: list[dict], limit: int = 10) -> None:
    base_url = cfg["site"]["base_url"].rstrip("/")
    site_title = cfg["site"].get("title", "Nompower")
    site_desc = cfg["site"].get("description", "Daily digest")

    items = sorted(articles, key=lambda a: a.get("published_ts", ""), reverse=True)[:limit]

    def rfc822(iso: str) -> str:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append("<rss version='2.0' xmlns:atom='http://www.w3.org/2005/Atom'>")
    parts.append("<channel>")
    parts.append(f"<title>{_html.escape(site_title)}</title>")
    parts.append(f"<link>{_html.escape(base_url + '/')}</link>")
    parts.append(f"<description>{_html.escape(site_desc)}</description>")
    parts.append(f"<lastBuildDate>{_html.escape(rfc822(now_utc_iso()))}</lastBuildDate>")

    for a in items:
        url = f"{base_url}{a['path']}"
        title = a.get("title", "")
        pub = a.get("published_ts", now_utc_iso())
        summary = a.get("summary", "") or ""
        if not summary:
            summary = re.sub(r"\s+", " ", re.sub(r"(?is)<[^>]+>", " ", a.get("body_html", ""))).strip()[:240]

        parts.append("<item>")
        parts.append(f"<title>{_html.escape(title)}</title>")
        parts.append(f"<link>{_html.escape(url)}</link>")
        parts.append(f"<guid isPermaLink='true'>{_html.escape(url)}</guid>")
        parts.append(f"<pubDate>{_html.escape(rfc822(pub))}</pubDate>")
        parts.append(f"<description>{_html.escape(summary)}</description>")
        parts.append("</item>")

    parts.append("</channel>")
    parts.append("</rss>")

    (SITE_DIR / "feed.xml").write_text("\n".join(parts) + "\n", encoding="utf-8")


def build_site(cfg: dict, articles: list[dict]) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "articles").mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "assets").mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "og").mkdir(parents=True, exist_ok=True)
    write_asset(SITE_DIR / "og" / "default.jpg", STATIC_DIR / "og" / "default.jpg")

    write_asset(SITE_DIR / "assets" / "style.css", STATIC_DIR / "style.css")
    write_asset(SITE_DIR / "assets" / "fx.js", STATIC_DIR / "fx.js")
    default_og = f"{base_url}/assets/og/default.jpg"

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

    write_rss_feed(cfg, articles, limit=10)

    base_ctx = {
        "site": cfg["site"],
        "ranking": ranking,
        "new_articles": new_articles,
        "ads_top": ADS_TOP,
        "ads_mid": ADS_MID,
        "ads_bottom": ADS_BOTTOM,
        "ads_rail_left": ads_rail_left,
        "ads_rail_right": ads_rail_right,
        "now_iso": now_utc_iso(),
    }

    render_to_file(
        jenv,
        "index.html",
        base_ctx,
        SITE_DIR / "index.html",
        "canonical": base_url + "/",
        "og_image": default_og,

    )

    static_pages = [
        ("about", "About Nompower", "<p>Nompower is a daily digest that curates a single noteworthy Reddit item and adds commentary, context, and takeaways.</p>"),
        ("privacy", "Privacy", "<p>We do not require accounts. Third-party ad scripts may set cookies or collect device identifiers. See each provider’s policy. If you want removal or have concerns, contact us.</p>"),
        ("terms", "Terms", "<p>Use at your own risk. Content is informational and may be incomplete. We link to sources and welcome corrections.</p>"),
        ("disclaimer", "Disclaimer", "<p>This site is not affiliated with Reddit. Trademarks belong to their owners. We do not guarantee accuracy, availability, or outcomes.</p>"),
        ("contact", "Contact", f"<p>Email: <a href='mailto:{cfg['site']['contact_email']}'>{cfg['site']['contact_email']}</a></p>"),
    ]

    for slug, title, body in static_pages:
        ctx = dict(base_ctx)
        ctx.update({"page_title": title, "page_body": body})
        render_to_file(
            jenv,
            "static.html",
            ctx,
            SITE_DIR / f"{slug}.html",
        )

    for a in articles:
        rel = related_articles(a, articles, k=6)
        ctx = dict(base_ctx)
        ctx.update(
            {
                "a": a,
                "related": rel,
                "policy_block": FIXED_POLICY_BLOCK.format(contact_email=cfg["site"]["contact_email"]),
            }
        )
        render_to_file(
            jenv,
            "article.html",
            ctx,
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
    body_html = strip_leading_duplicate_title(body_html, cand["title"])

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
