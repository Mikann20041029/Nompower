# nompower_pipeline/reddit.py
from __future__ import annotations

import requests


def _extract_reddit_media_image(post: dict) -> tuple[str, str]:
    """
    Returns (image_url, kind)
    kind: "reddit_image" | "reddit_gallery" | "none"

    Safety rule:
    - Accept ONLY images hosted on i.redd.it
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


def fetch_post_json(permalink: str) -> dict:
    """
    Fetch reddit post JSON and return metadata dict for pipeline.
    """
    url = permalink.rstrip("/") + ".json"
    r = requests.get(url, timeout=20, headers={"User-Agent": "NompowerBot/1.0"})
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
