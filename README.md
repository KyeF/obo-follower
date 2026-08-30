# obo-follower

A Python based terminal tool to track The Guardian's live over-by-over cricket commentary.

## Usage

### Fetch once and display all cached updates

```bash
./obo-follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" fetch
```

### Watch for new updates every 120 seconds (default)

```bash
./obo-follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" watch
```

### Watch with a custom polling interval (e.g. every 60 seconds)

```bash
./obo-follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" watch 60
```

### Dump the full JSON cache

```bash
./obo-follow.py "https://www.theguardian.com/sport/live/2026/aug/29/england-v-pakistan-second-mens-cricket-test-day-three-live" log
```

### Suppress ANSI colour codes

```bash
NO_COLOR=1 ./obo-follow.py <url> watch
```

Or redirect to a file:

```bash
./obo-follow.py <url> fetch > updates.txt
```

Colour is only emitted when stdout is a terminal; piping automatically disables it.

## Output Example

```
================================================================================
                    🏏 GUARDIAN CRICKET LIVE FEED
        Last updated: 2026-08-29T14:32:18.456789
================================================================================

📊 Total updates: 47

More rain! (blue)
And fifty to Lawrence (green)
47th over: England 177-7 (Lawrence 50, Robinson 2) (bold)
...

================================================================================
```

## Cache Location

Updates are stored in `~/.cricket-feed-<hash>.json` where `<hash>` is an 8-character MD5 hash of the URL. This allows tracking multiple matches simultaneously.

Example:

```
~/.cricket-feed-a1b2c3d4.json  # England v Pakistan
~/.cricket-feed-e5f6g7h8.json  # India v Australia
```

The JSON format is:

```json
[
  {
    "fetched_at": "2026-08-29T14:32:18.456789",
    "count": 3,
    "updates": [
      "WICKET! Atkinson LBW b Mohammad Ali 7 (England 162-7)",
      "More rain! (23 min delay)",
      "fifty to Lawrence (47th over: England 177-7)"
    ]
  }
]
```

## Design Notes

### Text extraction

The script extracts the `<h2>` heading and all `<p>` paragraphs from inside each `<article class="block ...">` element in the live blog. Since The Guardian auto-hashes CSS class names on each deploy (e.g. `dcr-1s160rg`, `dcr-up96pv`), the script matches structurally by tag name and the stable `block` class prefix, not by hashed classes.

### Clause-based colouring

Text is split into clauses at sentence boundaries (`!`, `.`, `?`) or before an over-header pattern. Each clause is independently scanned against a priority-ordered list of trigger patterns (WICKET, review, fifty, etc.). This allows a single update containing multiple events to be coloured correctly:

```
More rain! And fifty to Lawrence 47th over: England 177-7 (Lawrence 50, Robinson 2)
```

becomes:

- `More rain!` → blue
- `And fifty to Lawrence` → green
- `47th over: ...` → bold

### Polling strategy

The default 120-second interval balances responsiveness with politeness. No exponential backoff or jitter is implemented; the interval is fixed.

## Known limitations

### Guardian markup fragility

This is a screen-scraper, not an API consumer. Guardian's frontend markup can change without notice, breaking extraction. Mitigations:

- Structural matching (tag names, stable class prefixes) rather than exact selectors
- Diagnostic logging when no article blocks are found
- Minimal regex assumptions — the over-header pattern is the tightest constraint

If scraping breaks, check the live blog page in a browser and inspect an article block's structure.

### Text encoding artefacts

The Guardian's CMS and frontend rendering pipeline can introduce odd strings like `"double quotation mark"` (from accessibility text on pull-quote icons) or entities like `&quot;`. The `_clean_text()` method strips common ones, but edge cases may slip through.

### Timezone handling

All timestamps in the JSON cache are in the system's local time (ISO 8601 format). Match times referenced in commentary are typically BST, which may differ from your system clock. The script doesn't normalise these.

### No official API usage

The Guardian's Open Platform Content API doesn't expose live over-by-over commentary in real-time; it returns static article snapshots. This tool polls and diffs the live blog page instead, which is more responsive but less reliable.

## Troubleshooting

### No updates appear on `fetch`

1. Check the URL is correct and the match is currently live-blogged.
1. Enable debug logging: edit `logging.basicConfig(level=logging.DEBUG)` to see more detail.
1. Check the JSON cache: `./obo-follow.py <url> log | head -20`.
1. Inspect the Guardian page in a browser to confirm updates are appearing there.

### Colour codes leak into redirected output

The script detects whether stdout is a terminal and only emits ANSI codes in interactive mode. If colours still appear in piped output, ensure you're running the script directly (not through another layer like `tee` or a subshell that lies about TTY status).

### Script crashes on interrupted fetch

If the script is killed during a write (Ctrl-C during a save operation), the JSON file may be left in an inconsistent state. The `_load()` method has error recovery — it'll warn and start with an empty feed rather than crashing. Manually inspect `~/.cricket-feed-*.json` if concerned.

### Very old matches keep showing in `fetch`

The cache accumulates all updates from a match across multiple days. This is intentional (so you never lose history), but if the output gets unwieldy, delete the cache file and restart:

```bash
rm ~/.cricket-feed-<hash>.json
```

## Testing

Install pytest:

```bash
pip install pytest pytest-cov
```

Run the test suite:

```bash
pytest test_obo_follow.py -v
```

Check coverage:

```bash
pytest test_obo_follow.py --cov=obo_follow --cov-report=term-missing
```
