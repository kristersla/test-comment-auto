"""Read comments and replies from an Instagram Professional account you authorized.

This test uses Instagram API with Instagram Login, not Facebook Login.
Run: pip install requests && python export_instagram_comments.py
"""

import csv
import getpass
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

API_VERSION = "v26.0"
BASE_URL = f"https://graph.instagram.com/{API_VERSION}"
OUTPUT_DIR = Path(__file__).resolve().parent
COLUMNS = [
    "post_id", "post_url", "post_type", "post_timestamp", "comment_id",
    "parent_comment_id", "type", "username", "text", "timestamp",
]


def get_token():
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    env_path = OUTPUT_DIR / ".env"
    if not token and env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("IG_ACCESS_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"\'')
                break
    if not token:
        token = getpass.getpass("Paste your Instagram USER access token (input hidden): ").strip()
    if not token:
        raise ValueError("No token provided. An App Secret alone will not work.")
    return token


def api_error(response):
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    message = error.get("message", "Request rejected by Instagram")
    code = error.get("code", response.status_code)
    return RuntimeError(
        f"Instagram API error (HTTP {response.status_code}, code {code}): {message}\n"
        "Check token expiry, Instagram Login type, account role and the "
        "instagram_business_basic + instagram_business_manage_comments permissions."
    )


def get_json(session, url, params=None):
    # All calls, including paginated URLs, must be to Instagram's Graph API.
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "graph.instagram.com":
        raise RuntimeError("Instagram returned an unexpected pagination URL; stopping.")
    for attempt in range(3):
        try:
            response = session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Could not connect to Instagram: {type(exc).__name__}") from exc
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(2 ** attempt + 2)
            continue
        if not response.ok:
            raise api_error(response)
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Instagram returned a non-JSON response.") from exc
    raise RuntimeError("API request failed after retries.")


def paginated(session, endpoint, fields):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    params = {"fields": fields, "limit": 50}
    seen_urls = set()
    while url:
        if url in seen_urls:
            raise RuntimeError("Repeated pagination page encountered; stopping.")
        seen_urls.add(url)
        result = get_json(session, url, params=params)
        for item in result.get("data", []):
            yield item
        url = result.get("paging", {}).get("next")
        params = None  # paging.next already includes cursor and query parameters


def record(post, comment, kind, parent=""):
    return {
        "post_id": post.get("id", ""),
        "post_url": post.get("permalink", ""),
        "post_type": post.get("media_type", ""),
        "post_timestamp": post.get("timestamp", ""),
        "comment_id": comment.get("id", ""),
        "parent_comment_id": parent,
        "type": kind,
        "username": comment.get("username", ""),
        "text": comment.get("text", ""),
        "timestamp": comment.get("timestamp", ""),
    }


def main():
    token = get_token()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    profile = get_json(session, f"{BASE_URL}/me", {
        "fields": "user_id,username,account_type"
    })
    print(f"Connected: @{profile.get('username', '(unknown)')} [{profile.get('account_type', '')}]")
    print("Reading posts and comments. This may take a while for large profiles.\n")

    rows = []
    post_count = 0
    for post in paginated(session, "me/media", "id,permalink,media_type,timestamp"):
        post_count += 1
        count = 0
        for comment in paginated(session, f"{post['id']}/comments", "id,username,text,timestamp"):
            rows.append(record(post, comment, "comment"))
            count += 1
            for reply in paginated(session, f"{comment['id']}/replies", "id,username,text,timestamp"):
                rows.append(record(post, reply, "reply", parent=comment["id"]))
                count += 1
        print(f"Post {post_count}: {count} comment(s)/replies | {post.get('permalink', post['id'])}")
        time.sleep(0.1)

    csv_file = OUTPUT_DIR / "instagram_comments.csv"
    json_file = OUTPUT_DIR / "instagram_comments.json"
    with csv_file.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            # Protect spreadsheet applications from formulas in user comments.
            safe_row = {}
            for key, value in row.items():
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                safe_row[key] = value
            writer.writerow(safe_row)
    json_file.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone. Processed {post_count} post(s), exported {len(rows)} comments/replies.")
    print(f"CSV: {csv_file}\nJSON: {json_file}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyboardInterrupt) as exc:
        print(f"\nStopped: {exc}", file=sys.stderr)
        sys.exit(1)
