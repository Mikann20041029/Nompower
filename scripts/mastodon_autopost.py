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
log(issue_body[:800].replace("\n", "\\n"))

if not mastodon_base or not mastodon_token:
    fail("Missing secrets: MASTODON_BASE_URL or MASTODON_ACCESS_TOKEN")
if not deepseek_key:
    fail("Missing secret: DEEPSEEK_API_KEY")

# ---- 起動条件（Run status success + New article）----
# Markdownの **success** や success に両対応
if not re.search(r"Run status:\s*(?:\*+)?success(?:\*+)?\b", issue_body, re.IGNORECASE):
    log("Skip: Run status success not found (markdown-tolerant).")
    sys.exit(0)

if "New article:" not in issue_body:
    log("Skip: 'New article:' not found.")
    sys.exit(0)

# ---- 最新 New article URL 抽出 ----
matches = re.findall(r"New article:\s*(https?://\S+)", issue_body)
if not matches:
    fail("Parse failed: could not extract any New article URL")
article_url = matches[-1].strip()
log(f"Picked latest New article URL: {article_url}")

# ---- Issue本文から Title: を拾う（無ければIssueタイトル）----
m = re.search(r"^Title:\s*(.+)$", issue_body, re.MULTILINE)
article_title = m.group(1).strip() if m else issue_title.strip()
if not article_title:
    article_title = "New post"

log(f"Article title: {article_title}")

# ---- DeepSeekで“短めの人間文”を生成（リンク無し本文だけ生成させる）----
prompt = (
    "Write ONE short, very human-sounding English sentence for a Mastodon post.\n"
    "It should feel like a real person casually posting.\n"
    "Tone: witty, everyday-life vibe, slightly playful.\n"
    "Do NOT include any links, URLs, hashtags, emojis are optional (0-1 max).\n"
    "Do NOT mention AI.\n"
    "Keep it under 140 characters.\n\n"
    f"Context (article title): {article_title}\n"
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
one_liner = data["choices"][0]["message"]["content"].strip()
one_liner = re.sub(r"\s+", " ", one_liner).strip().strip('"').strip("'")

if not one_liner:
    fail("DeepSeek returned empty text")

log(f"Generated one-liner: {one_liner}")

# ---- 1発目投稿：文言 + URL（public）----
headers = {"Authorization": f"Bearer {mastodon_token}"}
post_url = f"{mastodon_base.rstrip('/')}/api/v1/statuses"

status1 = f"{one_liner}\n\n{article_url}"

r1 = requests.post(
    post_url,
    headers=headers,
    data={"status": status1, "visibility": "public"},
    timeout=20
)

log(f"Mastodon response1: {r1.status_code}")
if r1.status_code >= 300:
    fail(f"Mastodon post1 failed: {r1.status_code} {r1.text}")

j1 = r1.json()
log(f"Posted toot link: {j1.get('url')}")

# ---- 追加要件：15分後にリンク無しの“生活感＋ネタ全ぶり”投稿 ----
log("Sleeping 15 minutes...")
time.sleep(15 * 60)

prompt2 = (
    "Write a short, funny, very human English Mastodon post.\n"
    "Daily life vibe, casual, slightly chaotic, like a real person.\n"
    "Make it genuinely amusing.\n"
    "No links. No hashtags. No promotion. No mention of AI.\n"
    "Length: 1-3 short sentences.\n"
)

ds2 = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    headers={"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"},
    json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt2}],
        "temperature": 0.9,
    },
    timeout=30,
)

log(f"DeepSeek status (2nd): {ds2.status_code}")
if ds2.status_code >= 300:
    fail(f"DeepSeek API failed (2nd): {ds2.status_code} {ds2.text}")

text2 = ds2.json()["choices"][0]["message"]["content"].strip()
if not text2:
    fail("DeepSeek returned empty text (2nd)")

r2 = requests.post(
    post_url,
    headers=headers,
    data={"status": text2, "visibility": "public"},
    timeout=20
)

log(f"Mastodon response2: {r2.status_code}")
if r2.status_code >= 300:
    fail(f"Second Mastodon post failed: {r2.status_code} {r2.text}")

j2 = r2.json()
log(f"Posted 2nd toot link: {j2.get('url')}")

log("Done.")
