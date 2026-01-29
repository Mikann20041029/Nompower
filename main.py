import os
import requests
import random
import string
from datetime import datetime

# 設定
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GITHUB_TOKEN = os.getenv("GH_PAT")
REPO_NAME = "あなたのユーザー名/NumPower"

def generate_random_name(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_ai_content():
    # ここでDeepSeekを叩き、最新トレンドに合わせた「記事」と「釣り文句」を生成
    # 今回はテスト用に簡易的な内容にします
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "最新のAIツールを1つ選び、掲示板でクリックされる過激なタイトル3案と、そのツールの利点を日本語で短く出力せよ。"}]
    }
    res = requests.post(url, json=payload, headers=headers).json()
    return res['choices'][0]['message']['content']

def create_issue(title, body):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    data = {"title": title, "body": body}
    requests.post(url, json=data, headers=headers)

if __name__ == "__main__":
    content = get_ai_content()
    file_name = f"{generate_random_name()}.html"
    
    # 本来はここでHTMLファイルを生成してGitHubにプッシュする処理を入れる
    # 今回はIssueへの投稿を優先
    issue_title = f"【拡散指示】{datetime.now().strftime('%H:%M')} 生成完了"
    issue_body = f"生成URL: https://あなたのユーザー名.github.io/NumPower/{file_name}\n\n内容:\n{content}"
    
    create_issue(issue_title, issue_body)
    print("Issue作成完了")
