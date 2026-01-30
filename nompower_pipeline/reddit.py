# nompower_pipeline/reddit.py
from __future__ import annotations

from typing import List, Dict, Tuple
import re
import xml.etree.ElementTree as ET

import requests


_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)


def _extract_first_img_from_html(html: str) -> str:
    if not html:
        return ""
    m = _IMG_RE.search(html)
    if not m:
        return ""
    url = m.group(1).replace("&amp;", "&").strip()
    return url


def _safe_image(url: str) -> str:
    # safety: only accept reddit-hosted image to avoid mismatch
    if isinstance(url, str) and "i.redd.it/" in url:
        return url
    return ""


def fetch_rss_entries(rss_url: str, max_items: int = 25) -> List[Dict]:
    """
    Fetch Reddit RSS feed and return list of entries with keys:
    - title
    - link
    - summary (optional)
    - published (optional)
    - rss
    - hero_image (optional; SAFE: i.redd.it only)
    """
    r = requests.get(rss_url, timeout=25, headers={"User-Agent": "Mozilla/5.0 (NompowerBot/1.0)"})
    r.raise_for_status()

    root = ET.fromstring(r.text)

    ns = {
        "a": "http://www.w3.org/2005/Atom",
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
            link = (link_el.attrib.get("href") or "").strip()

        summary = (summary_el.text or "").strip() if summary_el is not None else ""
        published = (published_el.text or "").strip() if published_el is not None else ""

        # Atom content often holds HTML with an <img>
        content_html = ""
        content_el = ent.find("a:content", ns)
        if content_el is not None and content_el.text:
            content_html = content_el.text

        img = _extract_first_img_from_html(content_html) or _extract_first_img_from_html(summary)
        img = _safe_image(img)

        if not title or not link:
            continue

        entries.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "rss": rss_url,
                "hero_image": img,
                "hero_image_kind": "rss_i_redd_it" if img else "none",
            }
        )

        if len(entries) >= max_items:
            break

    return entries
