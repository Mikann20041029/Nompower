diff --git a/nompower_pipeline/generate.py b/nompower_pipeline/generate.py
index 1111111..2222222 100644
--- a/nompower_pipeline/generate.py
+++ b/nompower_pipeline/generate.py
@@ -1,6 +1,7 @@
 from __future__ import annotations

 from pathlib import Path
+from typing import Any
 from datetime import datetime, timezone
 from slugify import slugify
 import json
@@ -12,11 +13,12 @@ from .reddit import fetch_rss_entries, fetch_post_json
 from .render import env_for, render_to_file, write_asset

 CONFIG_PATH = ROOT / "nompower_pipeline" / "config.json"
 PROCESSED_PATH = ROOT / "processed_urls.txt"
 ARTICLES_PATH = ROOT / "data" / "articles.json"
+LAST_RUN_PATH = ROOT / "data" / "last_run.json"
 SITE_DIR = ROOT / "site"

 TEMPLATES_DIR = ROOT / "nompower_pipeline" / "templates"
 STATIC_DIR = ROOT / "nompower_pipeline" / "static"
@@ -205,6 +207,18 @@ def build_site(cfg: dict, articles: list[dict]) -> None:
     for a in articles:
         rel = related_articles(a, articles, k=6)
         render_to_file(jenv, "article.html", {
@@ -229,6 +243,23 @@ def build_site(cfg: dict, articles: list[dict]) -> None:
         }, SITE_DIR / a["path"].lstrip("/"))

+def write_last_run(cfg: dict, payload: dict[str, Any]) -> None:
+    base_url = cfg["site"]["base_url"].rstrip("/")
+    out = {
+        "updated_utc": now_utc_iso(),
+        "homepage_url": base_url + "/",
+        **payload
+    }
+    write_json(LAST_RUN_PATH, out)
+
 def main() -> None:
     cfg = load_config()
+    base_url = cfg["site"]["base_url"].rstrip("/")

     # state load
     processed = load_processed()
     articles = read_json(ARTICLES_PATH, default=[])
@@ -238,9 +269,19 @@ def main() -> None:
     cand = pick_candidate(cfg, processed, articles)
     if not cand:
         # 何も拾えない日でもサイトを再生成して整合性維持
         build_site(cfg, articles)
+        write_last_run(cfg, {
+            "created": False,
+            "article_url": "",
+            "article_title": "",
+            "source_url": "",
+            "note": "No new candidate found. Site rebuilt."
+        })
         return

     # generate article via DeepSeek
     body_html = deepseek_article(cfg, cand)
@@ -258,6 +299,7 @@ def main() -> None:
     slug = slugify(cand["title"])[:80] or f"post-{int(ts.timestamp())}"
     path = f"/articles/{ymd}-{slug}.html"
+    article_url = base_url + path

     entry = {
         "id": f"{ymd}-{slug}",
         "title": cand["title"],
@@ -280,6 +322,15 @@ def main() -> None:
     write_json(ARTICLES_PATH, articles)

     # rebuild site
     build_site(cfg, articles)
+    write_last_run(cfg, {
+        "created": True,
+        "article_url": article_url,
+        "article_path": path,
+        "article_title": cand["title"],
+        "source_url": cand["link"],
+        "subreddit": cand.get("subreddit",""),
+        "score": int(cand.get("score",0)),
+        "comments": int(cand.get("comments",0))
+    })

 if __name__ == "__main__":
     main()
