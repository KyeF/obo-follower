# obo-follower

A Python based terminal tool to track The Guardian's live over-by-over cricket commentary.

## Installation

Clone the repo and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Fetch once and display all cached updates

```bash
python3 obo_follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" fetch
```

### Watch for new updates every 120 seconds (default)

```bash
python3 obo_follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" watch
```

### Watch with custom polling interval (e.g., every 60 seconds)

```bash
python3 obo_follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" watch 60
```

### Watch with custom runtime limit (e.g., stop after 4 hours instead of default 9)

```bash
python3 obo_follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" watch --max-hours 4
```

### Dump the full JSON cache

```bash
python3 obo_follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" log
```

### Suppress ANSI colour codes

```bash
NO_COLOR=1 python3 obo_follow.py <url> watch
```

Or redirect to a file:

```bash
python3 obo_follow.py <url> fetch > updates.txt
```

**Note:** Colour is only emitted when stdout is a terminal. Piping or redirecting automatically disables ANSI codes.

## Output Example

```
================================================================================
                    🏏 GUARDIAN CRICKET LIVE FEED
        Last updated: 2026-08-31T19:31:44.324767
================================================================================

📊 Total updates: 47

More rain! (blue)
And fifty to Lawrence (green)
47th over: England 177-7 (Lawrence 50, Robinson 2) (bold)
...

================================================================================
```

## Cache Location

Updates are stored in a local `.cache/` folder within the project directory:

```
.cache/cricket-feed-a1b2c3d4.json  # England v Pakistan
.cache/cricket-feed-e5f6g7h8.json  # India v Australia
```

Each URL gets its own file (hash-based), allowing simultaneous tracking of multiple matches.

### JSON Format

```json
[
  {
    "fetched_at": "2026-08-31T19:30:00.000000",
    "count": 3,
    "updates": [
      "WICKET! Atkinson LBW b Mohammad Ali 7 (England 162-7)",
      "More rain! (23 min delay)",
      "Fifty to Lawrence 47th over: England 177-7"
    ]
  },
  {
    "fetched_at": "2026-08-31T19:32:00.000000",
    "count": 1,
    "updates": [
      "Bad light stops play at Chester-le-Street"
    ]
  }
]
```

## CLI Arguments

```
usage: obo_follow.py [-h] [--max-hours MAX_HOURS] url command [interval]

positional arguments:
  url                       URL of the Guardian live blog page
  command                   fetch (poll once), watch (poll repeatedly), or log (dump JSON)
  interval                  Polling interval in seconds for watch mode (default: 120)

optional arguments:
  --max-hours MAX_HOURS     Maximum watch runtime in hours before auto-stopping (default: 9)
  -h, --help                show this help message and exit
```

## Known Limitations

### Guardian Markup Fragility

This is a screen-scraper, not an API consumer. Guardian's frontend markup can change without notice, breaking extraction. Mitigations:

- Structural matching (tag names, stable class prefixes) rather than exact selectors
- Diagnostic logging when no article blocks are found
- Minimal regex assumptions

If scraping breaks, check the live blog page in a browser and inspect an article block's structure.

### Text Encoding Artefacts

The Guardian's CMS can introduce odd strings like `"double quotation mark"` (from accessibility text on pull-quote icons) or entities like `&quot;`. The `_clean_text()` method strips common ones, but edge cases may slip through.

### Timezone Handling

All timestamps in the JSON cache are in the system's local time (ISO 8601 format). Match times referenced in commentary are typically BST, which may differ from your system clock. The script doesn't normalise these.

### No Official API

The Guardian's Open Platform Content API doesn't expose live over-by-over commentary in real-time. This tool polls and diffs the live blog page instead, which is more responsive but less reliable.

## Troubleshooting

### No updates appear on `fetch`

1. Check the URL is correct and the match is currently live-blogged.
2. Enable debug logging: `logging.basicConfig(level=logging.DEBUG)` in `obo_follow.py`.
3. Check the JSON cache: `python3 obo_follow.py <url> log | head -20`.
4. Inspect the Guardian page in a browser to confirm updates are appearing there.

### Colour codes leak into redirected output

The script detects whether stdout is a terminal and only emits ANSI codes in interactive mode. If colours still appear in piped output, ensure you're running the script directly (not through another layer like `tee` or a subshell that lies about TTY status).

### Script crashes on interrupted fetch

If the script is killed during a write (Ctrl-C during a save operation), the JSON file may be left in an inconsistent state. The `_load()` method has error recovery — it'll warn and start with an empty feed rather than crashing.

### Very old matches keep showing in `fetch`

The cache accumulates all updates from a match across multiple days. This is intentional (so you never lose history), but if the output gets unwieldy, delete the cache file and restart:

```bash
rm .cache/cricket-feed-<hash>.json
```

Or remove the entire local cache:

```bash
rm -rf .cache/
```

## Testing

Install pytest:

```bash
pip install pytest pytest-timeout
```

Run the test suite:

```bash
pytest test_obo_follow.py -v
```


**Note:** This tool is for personal use. Respect The Guardian's terms of service when running automated scrapers. It's not cowardly to pray for rain.
