import os
import time
import re
import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["REPO"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]

MASTODON_BASE_URL = os.environ["MASTODON_BASE_URL"].rstrip("/")
MASTODON_ACCESS_TOKEN = os.environ["MASTODON_ACCESS_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

def get_latest_comment():
    url = f"https://api.github.com/repos/{REPO}/issues/{ISSUE_NUMBER}/comments"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    comments = r.json()
    return comments[-1]["body"] if comments else ""

def extract_article_url(text):
    if "Run status: success" not in text:
        return None
    m = re.search(r"New article:\s*(https?://\S+)", text)
    return m.group(1) if m else None

def post_mastodon(status):
    url = f"{MASTODON_BASE_URL}/api/v1/statuses"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"},
        data={"status": status},
    )
    r.raise_for_status()

def generate_fun_post():
    prompt = (
        "Write a short, casual, slightly funny English post about daily life. "
        "No links. 1–2 sentences. Friendly tone."
    )

    r = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def main():
    print("Fetching latest Issue comment...")
    body = get_latest_comment()

    article_url = extract_article_url(body)
    if not article_url:
        print("No valid New article URL found. Exit.")
        return

    print("Posting article URL to Mastodon...")
    post_mastodon(article_url)

    print("Waiting 15 minutes...")
    time.sleep(900)

    print("Generating second post...")
    fun_post = generate_fun_post()

    print("Posting second Mastodon post...")
    post_mastodon(fun_post)

    print("Done.")

if __name__ == "__main__":
    main()
