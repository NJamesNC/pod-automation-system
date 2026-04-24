#!/usr/bin/env python3
"""
Post "The Great Shepherd" carousel to Facebook via Blotato API.

Usage:
    python scripts/post_shepherd_carousel.py

Requires:
    - BLOTATO_API_KEY in .env (or environment)
    - pip install requests python-dotenv
    - Image files accessible at IMAGES_DIR (defaults to Windows path, override via SHEPHERD_IMAGES_DIR env var)
"""

import os
import sys
import time
import json
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional; fall back to os.environ

# ── Config ────────────────────────────────────────────────────────────────────

BLOTATO_API_KEY = os.getenv("BLOTATO_API_KEY", "")
BLOTATO_BASE_URL = "https://backend.blotato.com"

DEFAULT_IMAGES_DIR = r"C:\Users\mitia\OneDrive\Desktop\Reflect His Light Stuff\The Great Shepherd"
IMAGES_DIR = Path(os.getenv("SHEPHERD_IMAGES_DIR", DEFAULT_IMAGES_DIR))

IMAGE_FILES = [
    "01_title.png",
    "02_psalm23.png",
    "03_close.png",
    "04_promises.png",
    "05_ezekiel.png",
    "06_john10.png",
    "07_comparison.png",
    "08_fulfillment.png",
    "09_price.png",
    "10_come_home.png",
]

# Facebook pages to post to (Instagram already posted separately)
FACEBOOK_PAGES = [
    {"page_id": "1116499364871909", "name": "Reflect His Light LLC"},
    {"page_id": "1069607026233543", "name": "Reflect His Light Merch"},
]

CAPTION = """\
🐑 THE GREAT SHEPHERD — A Journey Through Scripture

From the fields of David to the promises of God.

Swipe through this full journey 👉

Psalm 23 promised: "The Lord is my shepherd."
Ezekiel 34 promised: "I myself will search for my sheep."
John 10 fulfilled it: "I am the Good Shepherd."

Seven promises. Every one kept.
Contentment. Rest. Restoration. Guidance.
Courage. Honor. Eternity.

2 Corinthians 5:21 — The price was paid.

The table is prepared. The cup is overflowing.
Just hear His voice — and follow. 🙏

Come home.

reflecthislightllc.com

#TheGreatShepherd #Psalm23 #JesusIsLord #ReflectHisLight #ChristianFaith"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def headers():
    return {
        "Content-Type": "application/json",
        "blotato-api-key": BLOTATO_API_KEY,
    }


def blotato_get(path):
    resp = requests.get(f"{BLOTATO_BASE_URL}{path}", headers=headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def blotato_post(path, payload):
    resp = requests.post(
        f"{BLOTATO_BASE_URL}{path}",
        headers=headers(),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def retry(fn, attempts=3, delay=2):
    """Call fn up to `attempts` times with exponential backoff."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if i == attempts - 1:
                raise
            wait = delay * (2 ** i)
            print(f"    Retry {i+1}/{attempts-1} after {wait}s ({exc})")
            time.sleep(wait)

# ── Core steps ────────────────────────────────────────────────────────────────

def list_accounts():
    data = blotato_get("/v2/users/me/accounts")
    return data.get("items", [])


def get_subaccounts(account_id):
    data = blotato_get(f"/v2/users/me/accounts/{account_id}/subaccounts")
    return data.get("items", [])


def find_account_id_for_page(accounts, target_page_id):
    """Walk all Facebook accounts and their subaccounts to match a page ID."""
    for account in accounts:
        if account.get("platform", "").lower() != "facebook":
            continue
        subs = get_subaccounts(account["id"])
        for sub in subs:
            if str(sub.get("id", "")) == str(target_page_id):
                return account["id"]
    return None


def upload_image(image_path: Path) -> str:
    """Upload a local image via Blotato presigned URL; returns public URL."""
    filename = image_path.name

    # Step 1 – request a presigned slot
    slot = blotato_post("/v2/media/uploads", {"filename": filename})
    presigned_url = slot["presignedUrl"]
    public_url = slot["publicUrl"]

    # Step 2 – PUT the raw bytes to S3
    with open(image_path, "rb") as fh:
        put_resp = requests.put(
            presigned_url,
            data=fh,
            headers={"Content-Type": "image/png"},
            timeout=120,
        )
        put_resp.raise_for_status()

    return public_url


def post_carousel(account_id, page_id, media_urls, page_name):
    payload = {
        "post": {
            "accountId": account_id,
            "content": {
                "text": CAPTION,
                "mediaUrls": media_urls,
                "platform": "facebook",
            },
            "target": {
                "targetType": "facebook",
                "pageId": page_id,
            },
        }
    }
    return blotato_post("/v2/posts", payload)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BLOTATO_API_KEY:
        sys.exit(
            "ERROR: BLOTATO_API_KEY is not set.\n"
            "Add it to your .env file:  BLOTATO_API_KEY=your_key_here"
        )

    print("=" * 60)
    print("  The Great Shepherd — Facebook Carousel Post")
    print("=" * 60)

    # ── 1. Verify image files exist ──────────────────────────────
    print("\n[1/4] Checking image files...")
    missing = [f for f in IMAGE_FILES if not (IMAGES_DIR / f).exists()]
    if missing:
        sys.exit(
            f"ERROR: {len(missing)} file(s) not found in {IMAGES_DIR}:\n"
            + "\n".join(f"  {f}" for f in missing)
        )
    print(f"      All {len(IMAGE_FILES)} images found in:\n      {IMAGES_DIR}")

    # ── 2. Resolve account IDs ───────────────────────────────────
    print("\n[2/4] Resolving Blotato account IDs for Facebook pages...")
    accounts = retry(list_accounts)
    print(f"      {len(accounts)} account(s) connected to Blotato")

    for page in FACEBOOK_PAGES:
        acct_id = find_account_id_for_page(accounts, page["page_id"])
        if not acct_id:
            sys.exit(
                f"ERROR: Could not find a Blotato accountId for page "
                f"{page['page_id']} ({page['name']}).\n"
                f"Make sure the Facebook account is connected in Blotato."
            )
        page["account_id"] = acct_id
        print(f"      {page['name']:35s}  pageId={page['page_id']}  accountId={acct_id}")

    # ── 3. Upload images ─────────────────────────────────────────
    print(f"\n[3/4] Uploading {len(IMAGE_FILES)} images to Blotato...")
    media_urls = []
    for i, filename in enumerate(IMAGE_FILES, 1):
        img_path = IMAGES_DIR / filename
        print(f"      [{i:02d}/{len(IMAGE_FILES)}] {filename} ...", end=" ", flush=True)
        url = retry(lambda p=img_path: upload_image(p))
        media_urls.append(url)
        print("done")
        time.sleep(0.3)

    print(f"\n      Upload complete. Public URLs:")
    for url in media_urls:
        print(f"        {url}")

    # ── 4. Post carousels ────────────────────────────────────────
    print(f"\n[4/4] Posting carousel to {len(FACEBOOK_PAGES)} Facebook page(s)...")
    results = []
    for page in FACEBOOK_PAGES:
        print(f"      → {page['name']} (page {page['page_id']}) ...", end=" ", flush=True)
        result = retry(
            lambda p=page: post_carousel(
                p["account_id"], p["page_id"], media_urls, p["name"]
            )
        )
        results.append({"page": page["name"], "result": result})
        print("posted!")
        time.sleep(1)

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  All done!")
    print("=" * 60)
    print("\nPost submission IDs:")
    for r in results:
        print(f"  {r['page']:35s}  {json.dumps(r['result'])}")
    print()


if __name__ == "__main__":
    main()
