import os
import re
import time
import sys
import requests

issue_title = os.getenv("ISSUE_TITLE", "")
issue_body = os.getenv("ISSUE_BODY", "")

mastodon_base = os.getenv("MASTODON_BASE_URL")
mastodon_token = os.getenv("MASTODON_ACCESS_TOKEN")
deepseek_key = os.getenv("DEEPSEEK_API_KEY")

def log(msg):
    print(f"[LOG] {msg}", flush=True)

def fail(msg):
    print(f"[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)

# ---- 条件チェック ----
if "Run status: success" not in issue_body:
    log("Run status: success not found. Exit.")
    sys.exit(0)

if "New article:" not in issue_body:
    log("New article not found. Exit.")
    sys.exit(0)

# ---- 最新の New article URL 抽出 ----
matches = re.findall(r"New article:\s*(https?://\S+)", issue_body)
if not matches:
    fail("New article URL parse failed.")

article_url = matches[-1]
log(f"Picked article URL: {article_url}")

# ---- Mastodon 投稿（URLあり）----
headers = {
    "Authorization": f"Bearer {mastodon_token}"
}

resp = requests.post(
    f"{mastodon_base}/api/v1/statuses",
    headers=headers,
    data={"status": article_url},
    timeout=20
)

if resp.status_code >= 300:
    fail(f"Mastodon post failed: {resp.status_code} {resp.text}")

log("Posted article URL to Mastodon.")

# ---- 15分待機 ----
log("Waiting 15 minutes before second post...")
time.sleep(15 * 60)

# ---- DeepSeekで文章生成 ----
prompt = """
Write a short, funny, very human English Mastodon post.
Daily life vibe, casual, slightly chaotic, like a real person.
No links. No hashtags. No promotion.
"""

ds_resp = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {deepseek_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9
    },
    timeout=30
)

if ds_resp.status_code >= 300:
    fail(f"DeepSeek API failed: {ds_resp.status_code} {ds_resp.text}")

text = ds_resp.json()["choices"][0]["message"]["content"].strip()
log(f"Generated text: {text}")

# ---- Mastodon 投稿（リンクなし）----
resp2 = requests.post(
    f"{mastodon_base}/api/v1/statuses",
    headers=headers,
    data={"status": text},
    timeout=20
)

if resp2.status_code >= 300:
    fail(f"Second Mastodon post failed: {resp2.status_code} {resp2.text}")

log("Posted second human-style post.")
