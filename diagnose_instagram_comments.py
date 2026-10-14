"""Diagnose empty Instagram comments responses without changing the account.

Run: py diagnose_instagram_comments.py
Requires requests (installed for the companion export script).
"""
import sys
import requests
from export_instagram_comments import BASE_URL, get_token, get_json


def main():
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {get_token()}"})

    print("\nChecking Instagram Login API (read-only)...")
    profile = get_json(session, f"{BASE_URL}/me", {"fields": "username,account_type"})
    print(f"Account: @{profile.get('username', 'unknown')} [{profile.get('account_type', 'unknown')}]")

    # The API may not expose /me/permissions for every token configuration.
    try:
        scopes = get_json(session, f"{BASE_URL}/me/permissions")
        values = scopes.get('data', [])
        if isinstance(values, list):
            for name in ("instagram_business_basic", "instagram_business_manage_comments"):
                entry = next((p for p in values if p.get('permission') == name), None)
                print(f"Scope {name}: {entry.get('status', 'present') if entry else 'not listed'}")
    except RuntimeError:
        print("Scope introspection not available for this token; continuing.")

    media = get_json(session, f"{BASE_URL}/me/media", {
        "fields": "id,permalink,comments_count", "limit": 50,
    })
    posts = media.get('data', [])
    print(f"Posts in first API page: {len(posts)}")
    if not posts:
        print("No posts returned. Stop here and inspect the account/token.")
        return

    selected = next((p for p in posts if (p.get('comments_count') or 0) > 0), posts[0])
    print(f"Selected post: {selected.get('permalink', '(no URL)')}")
    print(f"Instagram comments_count: {selected.get('comments_count', 'not returned')}")

    comments = get_json(session, f"{BASE_URL}/{selected['id']}/comments", {
        "fields": "id,username,text,timestamp", "limit": 25,
    })
    items = comments.get('data', [])
    paging = comments.get('paging') or {}
    print("Comments endpoint: HTTP 200")
    print(f"Returned comments: {len(items)}")
    print(f"Paging cursors present: {bool((paging.get('cursors') or {}))}")
    print(f"Next page URL present: {bool(paging.get('next'))}")

    if isinstance(selected.get('comments_count'), int) and selected['comments_count'] > 0 and not items:
        print("\nRESULT: The post reports existing comments, but the comments endpoint returned none.")
        print("This suggests an access/filtering or API behavior issue, not a post with no comments.")
        print("Next checks: app published/development status and token access level.")
    elif items:
        print("\nRESULT: Comment access is working for this post.")
    else:
        print("\nRESULT: Inconclusive. Select a post with visible comments or compare other posts.")

    print("\nDo not share your access token or app secret.")


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, requests.RequestException) as exc:
        print(f"\nAPI test stopped: {exc}", file=sys.stderr)
        sys.exit(1)
