import os
import re
import time
import requests
import sys

ISSUE_NUMBER = os.getenv("ISSUE_NUMBER", "")
ISSUE_TITLE = os.getenv("ISSUE_TITLE", "")
COMMENT_BODY = os.getenv("COMMENT_BODY", "")

# ===== 反応条件 =====
# 1) Issue #1 だけ
# 2) コメントに Run status: success がある
# 3) コメントに New article: がある
if ISSUE_NUMBER != "1":
    sys.exit(0)

if "Run status: success" not in COMMENT_BODY:
    sys.exit(0)

urls = re.findall(r"New article:\s*(https?://\S+)", COMMENT_BODY)
if not urls:
    sys.exit(0)

# コメント内の New article は基本1個なので [-1] でOK
article_url = urls[-1].strip()

BASE = os.environ["MASTODON_BASE_URL"].rstrip("/")
TOKEN = os.environ["MASTODON_ACCESS_TOKEN"]

def post_mastodon(text: str):
    r = requests.post(
        f"{BASE}/api/v1/statuses",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data={"status": text, "visibility": "public"},
        timeout=25,
    )
    print("Mastodon:", r.status_code, r.text[:200])
    r.raise_for_status()

# ===== 即時投稿（URLあり）=====
post_mastodon(
    "Found a useful article today.\n"
    "Quick share (testing my pipeline).\n"
    f"{article_url}"
)

# ===== 15分待つ =====
time.sleep(15 * 60)

# ===== DeepSeek 投稿（URLなし・生活感）=====
api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

if api_key:
    r = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
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
    text = r.json()["choices"][0]["message"]["content"].strip()
else:
    text = "Tried to be productive today. Ended up reorganizing tabs for 10 minutes. That counts, right?"

post_mastodon(text)
