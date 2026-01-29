from __future__ import annotations
import feedparser
import requests
from typing import Any
from .util import normalize_url

UA = "NompowerBot/1.0 (+https://nompower.mikanntool.com)"

def fetch_rss_entries(rss_url: str) -> list[dict[str, Any]]:
    feed = feedparser.parse(rss_url)
    out: list[dict[str, Any]] = []
    for e in getattr(feed, "entries", []) or []:
        link = normalize_url(getattr(e, "link", "") or "")
        title = (getattr(e, "title", "") or "").strip()
        summary = (getattr(e, "summary", "") or "").strip()
        published = (getattr(e, "published", "") or "").strip()
        out.append({"link": link, "title": title, "summary": summary, "published": published, "rss": rss_url})
    return out

def fetch_post_json(permalink: str) -> dict[str, Any] | None:
    # Reddit の公開JSON（1日1件なら負荷も低い）
    url = normalize_url(permalink) + ".json?raw_json=1"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200:
            return None
        j = r.json()
        post = j[0]["data"]["children"][0]["data"]
        return post
    except Exception:
        return None
