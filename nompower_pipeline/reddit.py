# nompower_pipeline/reddit.py
from __future__ import annotations

from typing import List, Dict, Tuple
import xml.etree.ElementTree as ET

import requests


def fetch_rss_entries(rss_url: str, max_items: int = 25) -> List[Dict]:
    """
    Fetch Reddit RSS feed and return list of entries with keys:
    - title
    - link
    - summary (optional)
    - published (optional)
    - rss (source feed url)
    """
    r = requests.get(rss_url, timeout=25, headers={"User-Agent": "NompowerBot/1.0"})
    r.raise_for_status()

    # Reddit RSS is Atom-like XML
    root = ET.fromstring(r.text)

    # namespaces (Atom)
    ns = {
        "a": "http://www.w3.org/2005/Atom",
        "m": "http://search.yahoo.com/mrss/",
        "c": "http://purl.org/rss/1.0/modules/content/",
    }

    entries: List[Dict] = []

    for ent in root.findall("a:entry", ns):
        title_el = ent.find("a:title", ns)
        link_el = ent.find("a:link", ns)
        summary_el = ent.find("a:summary", ns)
        published_el = ent.find("a:published", ns)

        title = (title_el.text or "").strip() if title_el is not None else ""
        link = ""
        if link_el is not None:
            # <link rel="alternate" href="..."/>
            link = (link_el.attrib.get("href") or "").strip()

        summary = (summary_el.text or "").strip() if summary_el is not None else ""
        published = (published_el.text or "").strip() if published_el is not None else ""

        if not title or not link:
            continue

        entries.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "rss": rss_url,
            }
        )

        if len(entries) >= max_items:
            break

    return entries


def _extract_reddit_media_image(post: dict) -> Tuple[str, str]:
    """
    Returns (image_url, kind)
    kind: "reddit_image" | "reddit_gallery" | "none"

    Safety rule:
    - Accept ONLY images hosted on i.redd.it (high relevance)
    - Do NOT use thumbnail (mismatch risk)
    - Do NOT use external OG preview images (mismatch risk)
    """

    # 1) Direct reddit-hosted image (best)
    direct = post.get("url_overridden_by_dest") or post.get("url") or ""
    if isinstance(direct, str) and "i.redd.it/" in direct:
        return direct, "reddit_image"

    # 2) Gallery (pick first i.redd.it image)
    if post.get("is_gallery") is True and isinstance(post.get("media_metadata"), dict):
        md = post["media_metadata"]
        for _, item in md.items():
            if not isinstance(item, dict):
                continue
            s = item.get("s", {})
            if not isinstance(s, dict):
                continue
            u = s.get("u", "")
            if isinstance(u, str) and u:
                u = u.replace("&amp;", "&")
                if "i.redd.it/" in u:
                    return u, "reddit_gallery"

    return "", "none"


def fetch_post_json(permalink: str) -> Dict:
    """
    Fetch reddit post JSON and return metadata dict used by pipeline.
    Must be compatible with generate.py import:
      from .reddit import fetch_rss_entries, fetch_post_json
    """
    url = permalink.rstrip("/") + ".json"
    r = requests.get(url, timeout=25, headers={"User-Agent": "NompowerBot/1.0"})
    r.raise_for_status()
    data = r.json()

    post = data[0]["data"]["children"][0]["data"]

    image_url, image_kind = _extract_reddit_media_image(post)

    return {
        "subreddit": post.get("subreddit", "") or "",
        "over_18": bool(post.get("over_18", False)),
        "score": int(post.get("score", 0) or 0),
        "num_comments": int(post.get("num_comments", 0) or 0),
        "image_url": image_url,
        "image_kind": image_kind,
    }
