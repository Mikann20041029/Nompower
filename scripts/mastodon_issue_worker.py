import os
import re
import time
import requests
import sys

EVENT_NAME = os.getenv("EVENT_NAME", "")
ISSUE_NUMBER = os.getenv("ISSUE_NUMBER", "")
ISSUE_TITLE = os.getenv("ISSUE_TITLE", "")
ISSUE_BODY = os.getenv("ISSUE_BODY", "") or ""
COMMENT_BODY = os.getenv("COMMENT_BODY", "") or ""

# Issue #1 以外は無視
if ISSUE_NUMBER != "1":
    sys.exit(0)

# issuesイベントなら本文、issue_commentならコメント本文を使う
text = ISSUE_BODY if EVENT_NAME == "issues" else COMMENT_BODY
if not text:
    sys.exit(0)

# 条件（あなたが指定したやつ）
if "Run status: success" not in text:
    sys.exit(0)

urls = re.findall(r"New article:\s*(https?://\S+)", text)
if not urls:
    sys.exit(0)

article_url = urls[-1].strip()

BASE = os.environ["MASTODON_BASE_URL"].rstrip("/")
TOKEN = os.environ["MASTODON_ACCESS_TOKEN"]

def post_mastodon(msg: str):
    r = requests.post(
        f"{BASE}/api/v1/statuses",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data={"status": msg, "visibility": "public"},
        timeout=25,
    )
    print("Mastodon:", r.status_code, r.text[:200])
    r.raise_for_status()

# 即時投稿（URLあり）
post_mastodon(
    "Found a useful article today.\n"
    "Quick share (testing my pipeline).\n"
    f"{article_url}"
)

# 15分後投稿（URLなし）
time.sleep(15 * 60)

api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
if api_key:
    r = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "Write a casual, human, slightly funny Mastodon post in English. No links. No hashtags."},
                {"role": "user", "content": "Daily life + a small joke. One short post under 250 characters."},
            ],
            "max_tokens": 120,
            "temperature": 0.9,
        },
        timeout=40,
    )
    print("DeepSeek:", r.status_code, r.text[:200])
    r.raise_for_status()
    text2 = r.json()["choices"][0]["message"]["content"].strip()
else:
    text2 = "Tried to be productive today… ended up organizing my downloads folder. Again."

post_mastodon(text2)
