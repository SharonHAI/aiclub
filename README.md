# aiclub — class registration watcher

Watches an [ExoClass](https://exoclass.com) group-management page for an open spot
and pushes a phone notification the moment one appears. It does **not** register or
pay for you — see "What this bot will not do" below.

Target page:
```
https://embed.exoclass.com/en/embed/provider/736809ef-680e-4d35-b447-3b3ba478948a/group-management/049608f6-26c4-40ba-9f2b-c266b1260b53
```

## How it works

- `.github/workflows/registration-watcher.yml` runs on a schedule (every 15 minutes)
  via GitHub Actions.
- `scripts/check_availability.py` opens the page in a headless browser (Playwright),
  reads the rendered text, and decides `open` vs `full` using two independent signals:
  1. None of the "full" text patterns (`Full group`, `complet`, `sold out`, `no places`)
     appear on the page.
  2. At least one register/sign-up button is present and **not** disabled.

  Both must agree before it calls the class "open" — this is deliberately conservative
  so a page hiccup or a text change doesn't fire a false alarm. If neither signal is
  readable at all (the page structure changed), the run logs a warning and does
  nothing rather than guessing.
- State is kept in `state/status.json` and committed back by the workflow, so you only
  get a notification on the **transition** into "open" (plus a repeat every run while
  it stays open, in case you miss the first one) — not one every 15 minutes while full.
- Notifications go out via [ntfy.sh](https://ntfy.sh) to the topic configured in the
  workflow file. Install the ntfy app (iOS/Android) or use the web app at
  `https://ntfy.sh/<topic>` and subscribe to that exact topic to receive the push.

## What this bot will not do

It will never fill in payment details or click the final "pay / confirm" button.
Registration for this class is a paid checkout — that's a real transaction that
needs your explicit action and your card, not code running unattended on a schedule.
Storing checkout credentials/payment info as GitHub Actions secrets so a bot could
complete that flow unattended is also a security exposure this repo intentionally
avoids. When the bot detects an open spot, it notifies you — you take it from there.

## First-time setup

1. **Verify the detection logic actually matches the live page.** This session's
   network sandbox couldn't reach `embed.exoclass.com` to inspect the real markup, so
   the text patterns above are a best guess based on prior manual observation of the
   page ("Full group!" text, disabled Register buttons). Before relying on this:
   - Go to the **Actions** tab → **registration watcher** → **Run workflow** → tick
     `debug` → Run.
   - Open the run, download the `debug-page` artifact, and check `page-text.txt` and
     `screenshot.png` against what `scripts/check_availability.py` is matching on.
   - If the real "full" wording or button markup differs, adjust the
     `FULL_TEXT_PATTERNS` / `REGISTER_BUTTON_PATTERN` env vars at the top of the
     workflow file (no code changes needed).
2. Subscribe to the ntfy topic named in the workflow file's `NTFY_TOPIC` env var
   (in the ntfy app: **+** → **Subscribe to topic** → paste the topic name).
   Because ntfy topics are unauthenticated, anyone who guesses the topic name could
   also see these notifications — it's a random string for that reason, but treat it
   as obscure, not secret. Rename it (edit `NTFY_TOPIC` in the workflow) any time.
3. The workflow needs `contents: write` (already set) to commit `state/status.json`
   updates back to the repo — no extra permissions setup needed.

## Manual run

Actions tab → **registration watcher** → **Run workflow**.

## Caveats

- GitHub's scheduler is best-effort: a `*/15 * * * *` cron can slip by several minutes
  under load, and GitHub auto-disables scheduled workflows after 60 days of repo
  inactivity (any commit, including the bot's own state commits, resets that clock —
  so this should keep itself alive as long as it's running).
- The organization's own waitlist is very likely still your fastest path to a spot —
  a human on their list can fill a cancellation before it ever reaches this page.
