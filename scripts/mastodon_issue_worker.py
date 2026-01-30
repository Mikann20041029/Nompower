import os
import re
import time
import requests

ISSUE_TITLE = os.getenv("ISSUE_TITLE", "")
ISSUE_BODY = os.getenv("ISSUE_BODY", "")
ISSUE_USER = os.getenv("ISSUE_USER", "")

BASE = os.environ["MASTODON_BASE_URL"].rstrip("/")
TOKEN = os.environ["MASTODON_ACCESS_TOKEN"]

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = (os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com/v1").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

# 1) Issue本文から New article / Title を抽出
m_url = re.search(r"New article:\s*(https?://\S+)", ISSUE_BODY)
if not m_url:
    print("No 'New article:' found. Exit.")
    raise SystemExit(0)

article_url = m_url.group(1).strip()

m_title = re.search(r"Title:\s*(.+)", ISSUE_BODY)
article_title = m_title.group(1).strip() if m_title else ""

# 2) Mastodon共通
def mastodon_headers():
    return {"Authorization": f"Bearer {TOKEN}"}

def mastodon_post(text: str, visibility="public"):
    r = requests.post(
        f"{BASE}/api/v1/statuses",
        headers=mastodon_headers(),
        data={"status": text, "visibility": visibility},
        timeout=25,
    )
    print("POST /statuses:", r.status_code, r.text[:200])
    r.raise_for_status()

def follow_account(account_id: str):
    r = requests.post(
        f"{BASE}/api/v1/accounts/{account_id}/follow",
        headers=mastodon_headers(),
        timeout=25,
    )
    print("POST /follow:", r.status_code, r.text[:200])
    r.raise_for_status()

# 3) 起動直後：ローカルTLから“最近動いてる人”を最大5人フォロー
def follow_5_active_users():
    try:
        tl = requests.get(
            f"{BASE}/api/v1/timelines/public",
            headers=mastodon_headers(),
            params={"local": "true", "limit": "40"},
            timeout=25,
        )
        print("GET /timelines/public:", tl.status_code)
        tl.raise_for_status()
        statuses = tl.json()
    except Exception as e:
        print("Timeline fetch failed:", e)
        return

    # 自分自身のIDを取って除外（取れない場合は除外せず続行）
    my_acct = None
    try:
        me = requests.get(f"{BASE}/api/v1/accounts/verify_credentials",
                          headers=mastodon_headers(), timeout=25)
        if me.ok:
            my_acct = me.json().get("acct")
    except Exception:
        pass

    picked = []
    seen = set()

    for st in statuses:
        acc = st.get("account") or {}
        acc_id = acc.get("id")
        acct = acc.get("acct")
        is_bot = acc.get("bot", False)

        if not acc_id or not acct:
            continue
        if my_acct and acct == my_acct:
            continue
        if is_bot:
            continue
        if acc_id in seen:
            continue

        seen.add(acc_id)
        picked.append(acc_id)
        if len(picked) >= 5:
            break

    for acc_id in picked:
        try:
            follow_account(acc_id)
        except Exception as e:
            print("Follow failed:", e)

# 4) 起動直後：記事URLを「リンクだけ」にならない短文で投稿
def post_article_link():
    # スパムっぽく見えない最低限：価値1文＋補足1文＋URL
    # タイトルが取れてたら自然に混ぜる
    if article_title:
        lead = f"New read: {article_title}"
    else:
        lead = "New read (quick summary inside)."

    text = (
        f"{lead}\n"
        "I’m collecting one useful link at a time and sharing the key takeaway.\n"
        f"{article_url}\n"
        "#webdev #indiedev"
    )
    mastodon_post(text)

# 5) 15分後：DeepSeekに“生活感＋軽い笑い（英語）”の短文を作らせて投稿（URL無し）
def deepseek_chat(prompt: str) -> str:
    if not DEEPSEEK_KEY:
        return ""

    # OpenAI互換っぽい形（DeepSeek側が違っても secretsで差し替え可能）
    url = f"{DEEPSEEK_BASE}/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "You write natural, friendly English posts for Mastodon. No hype, no spam, no hashtags unless asked."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "max_tokens": 120,
    }
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=40,
    )
    print("DeepSeek:", r.status_code, r.text[:200])
    r.raise_for_status()
    data = r.json()
    return (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "").strip()

def post_15min_lifestyle_funny():
    prompt = (
        "Write ONE short Mastodon post in English (max 250 characters). "
        "It should feel like a real person: a tiny slice of daily life + a small joke. "
        "No links, no promotion, no hashtags. "
        "Make it friendly and not cringey."
    )
    text = deepseek_chat(prompt)
    if not text:
        # DeepSeek無い時は固定文で逃げる（壊れないため）
        text = "Tried to act productive today… ended up reorganizing my browser tabs for 20 minutes. That counts as cardio, right?"
    mastodon_post(text)

def main():
    # 誤爆防止（GitHub Actions botが作ったIssue以外でも本文に New article があれば動くが、最低限タイトルで絞る）
    if "Nompower" not in ISSUE_TITLE:
        print("Issue title doesn't look like target. Exit.")
        raise SystemExit(0)

    # Run status: success のときだけ動かしたいならこれを有効化
    if "Run status: success" not in ISSUE_BODY:
        print("Run status is not success. Exit.")
        raise SystemExit(0)

    follow_5_active_users()
    post_article_link()

    print("Sleeping 15 minutes...")
    time.sleep(15 * 60)

    post_15min_lifestyle_funny()

if __name__ == "__main__":
    main()
