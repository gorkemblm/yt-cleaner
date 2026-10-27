# yt-cleaner

A small Python script that **unsubscribes from every channel** and **empties the Watch Later list** on a YouTube account.

The official YouTube Data API cannot access Watch Later, and its daily quota allows only about 200 unsubscribes. This script uses Playwright to drive a real Chrome window instead: it clicks the buttons, opens the menus, and confirms the dialogs for you.

## Features

- Unsubscribes from all channels.
- Empties the Watch Later list.
- Supports multiple channels / Brand Accounts. You select the account to clean, and the script asks for confirmation before it starts.
- `--dry-run`: counts items without deleting anything.
- `--backup`: saves the lists as CSV files before deleting.
- The script never sees your password. You sign in yourself in the browser.

## Requirements

- Python 3.9+
- Google Chrome (installed on the system)

## Installation

```bash
git clone https://github.com/gorkemblm/yt-cleaner.git
cd yt-cleaner
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

On Windows, use `.venv\Scripts\` instead of `.venv/bin/`.

## Usage

```bash
.venv/bin/python yt_cleaner.py --dry-run            # count only, delete nothing
.venv/bin/python yt_cleaner.py --backup             # save a backup, then clean everything
.venv/bin/python yt_cleaner.py                      # subscriptions + Watch Later
.venv/bin/python yt_cleaner.py --only subs          # subscriptions only
.venv/bin/python yt_cleaner.py --only wl            # Watch Later only
.venv/bin/python yt_cleaner.py --delay 0.3          # faster (default: 0.6 s)
```

### Steps

1. The script opens a Chrome window.
2. Sign in to your Google account. If you have more than one channel, click **profile picture → Switch account** (top right) and select the channel to clean.
3. Return to the terminal and press **Enter**.
4. The script shows the active account name. If it is correct, type `y`.
5. Wait until the script finishes. Press `Ctrl+C` to stop at any time.

Your session is stored in `~/.yt-cleaner-profile`, so you do not need to sign in again next time. Delete that folder to remove the session.

### Duration

About 1–2 seconds per item. For example, 400 subscriptions and 850 videos take about 30 minutes in total.

## Known limitations

- **Deletion cannot be undone.** If you are not sure, run with `--dry-run` first, then with `--backup`.
- The script depends on the YouTube web UI. If YouTube changes its UI, the selectors may need an update.
- The script opens YouTube with `?hl=tr` (Turkish UI), so the selectors match on any account language. It was tested with the Turkish UI.
- If some items fail, run the script again. Items that are already cleaned are skipped.
- Browser automation may conflict with the YouTube Terms of Service. Use it on your own account, at your own risk.

## License

[MIT](LICENSE)
