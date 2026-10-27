#!/usr/bin/env python3
"""Unsubscribe from all YouTube channels and clear the Watch Later list.

Usage:
    .venv/bin/python yt_cleaner.py --dry-run        # count only, delete nothing
    .venv/bin/python yt_cleaner.py                  # subscriptions + Watch Later
    .venv/bin/python yt_cleaner.py --only subs      # subscriptions only
    .venv/bin/python yt_cleaner.py --only wl        # Watch Later only
    .venv/bin/python yt_cleaner.py --backup         # save a CSV backup before deleting

The browser profile is stored in ~/.yt-cleaner-profile.
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path.home() / ".yt-cleaner-profile"
BACKUP_DIR = Path(__file__).resolve().parent / "backups"

# hl=tr forces the Turkish UI regardless of the account language. The selectors
# below were verified against the Turkish UI, so they match on every account.
SUBS_URL = "https://www.youtube.com/feed/channels?hl=tr"
WL_URL = "https://www.youtube.com/playlist?list=WL&hl=tr"

UNSUB_TEXT = re.compile(r"^\s*(abonelikten çık|unsubscribe)\s*$", re.I)
WL_REMOVE_TEXT = re.compile(r"listesinden kaldır|remove from", re.I)

MENU_ITEMS = (
    "ytd-menu-popup-renderer ytd-menu-service-item-renderer, "
    "tp-yt-iron-dropdown yt-list-item-view-model, "
    "tp-yt-iron-dropdown ytd-menu-service-item-renderer"
)


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def scroll_to_end(page, item_selector, max_rounds=200):
    """Scroll until lazy loading stops. Return the number of loaded items."""
    last, stable = -1, 0
    for _ in range(max_rounds):
        count = page.locator(item_selector).count()
        if count == last:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        last = count
        page.mouse.wheel(0, 20000)
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")
    return last


def write_csv(name, header, rows):
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    log(f"Backup written: {path}")


def click_menu_item(page, pattern, timeout=4000):
    """Click the item in the open popup menu whose text matches pattern."""
    item = page.locator(MENU_ITEMS).filter(has_text=pattern).locator("visible=true").first
    item.wait_for(state="visible", timeout=timeout)
    item.click()


def safe_goto(page, url, retries=3):
    """Open a page. YouTube is sometimes slow, so retry on timeout."""
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="commit", timeout=60000)
            return True
        except PWTimeout:
            log(f"Page did not load ({attempt}/{retries}), retrying...")
            page.wait_for_timeout(5000)
    return False


def confirm_account(page):
    safe_goto(page, "https://www.youtube.com/?hl=tr")
    print()
    print("=" * 64)
    print("In the browser window:")
    print("  1. Sign in to your Google account (if needed).")
    print("  2. Click your profile picture (top right) > 'Switch account'")
    print("     and select the channel/account you want to clean.")
    print("When ready, come back here and press Enter.")
    print("=" * 64)
    input()

    name, handle = "?", "?"
    try:
        page.locator("button#avatar-btn").click(timeout=5000)
        header = page.locator("ytd-active-account-header-renderer")
        header.wait_for(timeout=5000)
        name = header.locator("#account-name").inner_text().strip()
        handle = header.locator("#channel-handle").inner_text().strip()
        page.keyboard.press("Escape")
    except PWTimeout:
        log("Could not read the active account (maybe not signed in).")

    ans = input(f"\nActive account: {name} ({handle})\nContinue with this account? [y/N]: ")
    if ans.strip().lower() not in ("y", "yes"):
        log("Cancelled.")
        sys.exit(1)


def clean_subscriptions(page, dry_run, delay, backup):
    log("Loading subscriptions...")
    safe_goto(page, SUBS_URL)
    item_sel = "ytd-channel-renderer"
    try:
        page.locator(item_sel).first.wait_for(timeout=20000)
    except PWTimeout:
        log("No subscriptions found.")
        return
    total = scroll_to_end(page, item_sel)
    log(f"Found {total} subscriptions.")
    if backup:
        rows = page.eval_on_selector_all(
            item_sel,
            """els => els.map(e => [
                (e.querySelector('#channel-title #text, #channel-title')?.innerText || '').trim(),
                e.querySelector('a#main-link, a.channel-link')?.href || ''
            ])""",
        )
        write_csv("subscriptions", ["channel", "url"], rows)
    if dry_run:
        return

    done = failed = 0
    channels = page.locator(item_sel)
    for i in range(channels.count()):
        ch = channels.nth(i)
        # A subscribed channel has the "subscribed" attribute on its subscribe button renderer.
        if ch.locator("ytd-subscribe-button-renderer[subscribed]").count() == 0:
            continue
        # Flow: visible "subscribed" (bell) button -> "Unsubscribe" in the menu -> confirm dialog.
        # The hidden "Unsubscribe from X." button cannot be clicked; it is read only for the channel name.
        hidden = ch.locator("ytd-subscribe-button-renderer button[aria-label*='aboneliğinden çık']").first
        title = (hidden.get_attribute("aria-label") or f"#{i}").replace(" aboneliğinden çık.", "")
        bell = ch.locator(
            "ytd-subscribe-button-renderer button"
            ":not([aria-label*='aboneliğinden']):not([aria-label^='Unsubscribe'])"
        ).locator("visible=true").first
        try:
            bell.scroll_into_view_if_needed(timeout=5000)
            bell.click(timeout=5000)
            click_menu_item(page, UNSUB_TEXT)
            confirm = page.locator(
                "yt-confirm-dialog-renderer button[aria-label='Abonelikten çık'], "
                "yt-confirm-dialog-renderer button[aria-label='Unsubscribe']"
            ).locator("visible=true").first
            confirm.wait_for(timeout=5000)
            confirm.click()
            ch.locator("ytd-subscribe-button-renderer:not([subscribed])").wait_for(timeout=5000)
            done += 1
            log(f"[{done}/{total}] Unsubscribed: {title}")
        except PWTimeout:
            failed += 1
            log(f"Failed: {title}")
            page.keyboard.press("Escape")
        time.sleep(delay)

    log(f"Subscriptions done. Unsubscribed: {done}, failed: {failed}.")
    if failed:
        log("Run the script again to retry the failed ones.")


def clean_watch_later(page, dry_run, delay, backup):
    log("Loading Watch Later...")
    safe_goto(page, WL_URL)
    item_sel = "ytd-playlist-video-renderer"
    try:
        page.locator(item_sel).first.wait_for(timeout=20000)
    except PWTimeout:
        log("Watch Later is empty.")
        return
    if dry_run or backup:
        log(f"Found {scroll_to_end(page, item_sel)} videos.")
    if backup:
        rows = page.eval_on_selector_all(
            item_sel,
            """els => els.map(e => [
                (e.querySelector('#video-title')?.innerText || '').trim(),
                (e.querySelector('#video-title')?.href || '').split('&')[0]
            ])""",
        )
        write_csv("watch_later", ["video", "url"], rows)
    if dry_run:
        return

    done = fails_in_row = 0
    while True:
        items = page.locator(item_sel)
        if items.count() == 0:
            # The visible list is empty; reload to check for remaining items.
            safe_goto(page, WL_URL)
            try:
                page.locator(item_sel).first.wait_for(timeout=15000)
            except PWTimeout:
                break
            continue

        item = items.first
        try:
            # YouTube reuses list elements, so verify the removal by video ID.
            href = item.locator("a#video-title").get_attribute("href", timeout=5000) or ""
            vid = re.search(r"v=([\w-]+)", href).group(1)
            item.scroll_into_view_if_needed(timeout=5000)
            item.hover()
            item.locator("#menu button").first.click(timeout=5000)
            click_menu_item(page, WL_REMOVE_TEXT)
            page.wait_for_function(
                """vid => ![...document.querySelectorAll('ytd-playlist-video-renderer a#video-title')]
                    .some(a => (a.getAttribute('href') || '').includes('v=' + vid))""",
                arg=vid,
                timeout=5000,
            )
            done += 1
            fails_in_row = 0
            log(f"[{done}] Removed")
        except (PWTimeout, AttributeError):
            fails_in_row += 1
            page.keyboard.press("Escape")
            if fails_in_row >= 5:
                log("5 failures in a row, stopping. Run the script again.")
                break
            safe_goto(page, WL_URL)
            page.wait_for_timeout(2000)
        time.sleep(delay)

    log(f"Watch Later done. Removed: {done}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Delete nothing, only count")
    ap.add_argument("--backup", action="store_true", help="Save the lists as CSV files in backups/ before deleting")
    ap.add_argument("--only", choices=["all", "subs", "wl"], default="all")
    ap.add_argument("--delay", type=float, default=0.6, help="Wait between actions (seconds)")
    args = ap.parse_args()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            channel="chrome",  # system Chrome; Google sign-in may block bundled Chromium
            headless=False,
            locale="tr-TR",
            viewport={"width": 1280, "height": 900},
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            confirm_account(page)
            if args.dry_run:
                log("DRY RUN: nothing will be deleted.")
            if args.only in ("all", "subs"):
                clean_subscriptions(page, args.dry_run, args.delay, args.backup)
            if args.only in ("all", "wl"):
                clean_watch_later(page, args.dry_run, args.delay, args.backup)
        except KeyboardInterrupt:
            log("Stopped by user.")
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
