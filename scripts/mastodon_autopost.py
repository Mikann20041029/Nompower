import os
import re
import time
import sys
import requests

def log(msg):
    print(f"[LOG] {msg}", flush=True)

def fail(msg):
    print(f"[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)

issue_title = os.getenv("ISSUE_TITLE", "")
issue_body = os.getenv("ISSUE_BODY", "") or ""
issue_number = os.getenv("ISSUE_NUMBER", "")
issue_user = os.getenv("ISSUE_USER", "")

mastodon_base = os.getenv("MASTODON_BASE_URL")
mastodon_token = os.getenv("MASTODON_ACCESS_TOKEN")
deepseek_key = os.getenv("DEEPSEEK_API_KEY")

log(f"Issue #{issue_number} by {issue_user}")
log(f"Issue title: {issue_title}")
log("Issue body head:")
log(issue_body[:500].replace("\n", "\\n"))

if not mastodon_base or not mastodon_token:
    fail("Missing secrets: MASTODON_BASE_URL or MASTODON_ACCESS_TOKEN")

if not deepseek_key:
    fail("Missing secret: DEEPSEEK_API_KEY")

# 起動条件
import re

if not re.search(r"Run status:\s*(?:\*+)?success(?:\*+)?", issue_body, re.IGNORECASE):
    log("Skip: Run status success not found (markdown-tolerant).")
    sys.exit(0)



if "New article:" not in issue_body:
    log("Skip: 'New article:' not found.")
    sys.exit(0)

# 最新の New article URL
matches = re.findall(r"New article:\s*(https?://\S+)", issue_body)
if not matches:
    fail("Parse failed: could not extract any New article URL")

article_url = matches[-1].strip()
log(f"Picked latest New article URL: {article_url}")

# Mastodon post 1: URLのみ（あなたの要件通り）
headers = {"Authorization": f"Bearer {mastodon_token}"}
post_url = f"{mastodon_base.rstrip('/')}/api/v1/statuses"

r1 = requests.post(post_url, headers=headers, data={"status": article_url}, timeout=20)
log(f"Mastodon response1: {r1.status_code}")
if r1.status_code >= 300:
    fail(f"Mastodon post1 failed: {r1.status_code} {r1.text}")

log("Posted URL to Mastodon.")

# 15分待つ
log("Sleeping 15 minutes...")
time.sleep(15 * 60)

# DeepSeekで“人間っぽい生活ネタ投稿”生成（リンク無し）
prompt = (
    "Write a short, funny, very human English Mastodon post.\n"
    "Daily life vibe, casual, slightly chaotic, like a real person.\n"
    "Make it genuinely amusing.\n"
    "No links. No hashtags. No promotion. No mention of AI.\n"
    "Length: 1-3 short paragraphs."
)

ds = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    headers={"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"},
    json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
    },
    timeout=30,
)

log(f"DeepSeek status: {ds.status_code}")
if ds.status_code >= 300:
    fail(f"DeepSeek API failed: {ds.status_code} {ds.text}")

data = ds.json()
text = data["choices"][0]["message"]["content"].strip()
if not text:
    fail("DeepSeek returned empty text")

log("Generated second post text (head):")
log(text[:300].replace("\n", "\\n"))

r2 = requests.post(post_url, headers=headers, data={"status": text}, timeout=20)
log(f"Mastodon response2: {r2.status_code}")
if r2.status_code >= 300:
    fail(f"Mastodon post2 failed: {r2.status_code} {r2.text}")

log("Posted second post to Mastodon.")
