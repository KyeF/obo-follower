#!/usr/bin/env python3
"""Watch a Guardian cricket live blog and stream new over-by-over commentary updates to the terminal."""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep, time

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("obo-follower")

# ANSI colour codes
COLOURS = {
    "RED": "\033[91m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "ORANGE": "\033[38;5;208m",
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "ITALIC": "\033[3m",
    "UNDERLINE": "\033[4m",
}

MIN_UPDATE_LENGTH = 40
DISPLAY_LIMIT = 30
DEFAULT_INTERVAL = 120


class CricketFeedTracker:
    """Fetch and persist updates from a Guardian live cricket blog."""

    def __init__(self, url: str) -> None:
        """Initialise tracker with URL and set up persistent storage.

        Args:
            url: The Guardian live blog URL to track.
        """
        self.url = url
        self._use_colour = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
        h = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:8]
        # Store cache files in local .cache directory
        self.cache_dir = Path.cwd() / ".cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.log_path = self.cache_dir / f"cricket-feed-{h}.json"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "obo-follower/0.1 (personal use)"})
        self.feed: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load feed from disk, normalising old string format to new dict format."""
        if not self.log_path.exists():
            self.feed = []
            return

        try:
            with self.log_path.open() as f:
                raw_feed = json.load(f)

                if not isinstance(raw_feed, list):
                    logger.warning(
                        f"Feed file contains {type(raw_feed).__name__}, "
                        f"expected list; starting fresh",
                    )
                    self.feed = []
                    return

                # Normalise old format (strings) to new format (dicts)
                self.feed = [
                    b
                    if isinstance(b, dict)
                    else {
                        "fetched_at": None,
                        "count": 1,
                        "updates": [b],
                    }
                    for b in raw_feed
                ]
                # Sort by fetched_at to ensure chronological order across multiple runs
                self.feed.sort(key=lambda batch: batch.get("fetched_at") or "", reverse=False)
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.warning(
                f"Could not read {self.log_path} ({e}); starting with empty feed",
            )
            self.feed = []

    def _save(self) -> None:
        """Atomically write feed to disk using temp file + rename."""
        tmp = self.log_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.feed, indent=2))
        tmp.replace(self.log_path)

    def _colourise_text(self, text: str) -> str:
        """Apply colour coding to key events across an entire update.

        Splits the text into clauses (at sentence punctuation or before an
        over header) and colourises each clause independently, so multiple
        distinct events in one update (e.g. a rain delay followed by a fifty)
        each get their own colour.

        Args:
            text: The update text to potentially highlight.

        Returns:
            The text with ANSI colour codes applied per clause (or unchanged
            if no TTY is attached).
        """
        if not self._use_colour:
            return text

        # A clause ends at sentence punctuation, or right before an over header
        # begins (over headers often run straight on from the previous clause
        # with no punctuation between them, e.g. "...Lawrence 47th over: ...").

        boundary = re.compile(
            r"(?<!wicket)[!.?]\s*|(?<!\d)(?=\d+(?:st|nd|rd|th)\s+over:)|(?<=\))\s*(?=[A-Z])",
            re.IGNORECASE,
        )

        cut_points = [0]
        for m in boundary.finditer(text):
            cut_points.append(m.end())
        cut_points.append(len(text))

        clauses = [
            text[cut_points[i] : cut_points[i + 1]]
            for i in range(len(cut_points) - 1)
            if cut_points[i] < cut_points[i + 1]
        ]

        return "".join(self._colourise_clause(clause) for clause in clauses)

    def _colourise_clause(self, clause: str) -> str:
        """Highlight a single clause with its own colour, if a trigger phrase is found.

        Args:
            clause: A single sentence/segment of an update.

        Returns:
            The clause with ANSI colour codes applied around the matched phrase.
        """
        RED = COLOURS["RED"]
        GREEN = COLOURS["GREEN"]
        YELLOW = COLOURS["YELLOW"]
        BLUE = COLOURS["BLUE"]
        ORANGE = COLOURS["ORANGE"]
        RESET = COLOURS["RESET"]
        BOLD = COLOURS["BOLD"]
        ITALIC = COLOURS["ITALIC"]
        UNDERLINE = COLOURS["UNDERLINE"]

        # Checked in priority order; first match wins for this clause.
        # Empty colour string ("") means bold-only, no colour.
        rules: list[tuple[str, str]] = [
            (r"wicket!.*?(?:\d+-\d+)?(?:\))?", RED + BOLD),
            (r".*not out!", GREEN + BOLD),
            (r".*review.*", YELLOW + BOLD),
            (r"rain stops play.*", BLUE + BOLD),
            (r"more rain.*", BLUE + BOLD),
            (r"bad light stops play.*", ORANGE + BOLD),
            (r"^stumps\b[!:].*", ORANGE + BOLD),
            (r"abandoned.*", RED + BOLD),
            (r"fifty (?:to|for).*", GREEN + BOLD),
            (r"hundred (?:to|for).*", GREEN + BOLD),
            (r"\b\w+ need \d+ to win\b", GREEN + BOLD),
            (r"\b\w+ win(?:s|ning)?\b(?: by \d+)?(?:[^.!?]*)?", GREEN + BOLD),
            (r"\b\w+ los(?:e|ing|es)?\b(?: by \d+)?(?:[^.!?]*)?", RED + BOLD),
            (r"(?:man|woman) of the match is \w+ \w+|\w+ \w+ is (?:man|woman) of the match", GREEN + BOLD),
            (r"^(?:lunch|tea)\b.*?\d+-\d+|^(?:lunch|tea)\b.*", BOLD + ITALIC + UNDERLINE),
            (r"\d+(?:st|nd|rd|th)\s+over:[^(]*(?:\([^)]+\))?", BOLD),
        ]

        for pattern, style in rules:
            match = re.search(pattern, clause, re.IGNORECASE)
            if match:
                highlighted = f"{style}{match.group()}{RESET}"
                return clause.replace(match.group(), highlighted, 1)

        return clause

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text without adding formatting.

        Args:
            text: Raw text from the live blog.

        Returns:
            Cleaned text with artefacts removed and whitespace normalised.
        """
        text = text.replace("double quotation mark", '"')
        text = text.replace("&quot;", '"')
        text = text.replace("&amp;", "&")
        text = text.replace("View image in fullscreen", "")
        text = text.replace("Photograph:", "Photo:")
        text = text.replace("Share Updated at", "")
        text = text.replace("Share", "")
        # Match time patterns: "4m ago", "14h ago", "30s ago", "14.31 BST" etc
        text = re.sub(r"^(\d+[smh]\s+ago\s+\d+\.\d+\s+BST\s+)", "", text)
        text = re.sub(r"^(\d+[smh]\s+ago\s+)", "", text)

        # Insert missing spaces around punctuation/number boundaries
        text = re.sub(r":(?=[A-Za-z0-9])", ": ", text)  # "Chelmsford:Essex" -> "Chelmsford: Essex"
        text = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", text)  # "shire84-0" -> "shire 84-0"
        text = re.sub(r"(?<=[0-9])(?=[A-Za-z])", " ", text)  # "250Durham" -> "250 Durham"
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)  # "vHampshire" -> "v Hampshire"

        # Replace multiple spaces/newlines with single space (preserves single spaces)
        text = re.sub(r"(?<=\))(?=[A-Z])", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_all_updates(self) -> list[str]:
        """Extract updates from HTML article blocks.

        Returns:
            List of cleaned update texts in chronological order (oldest first).

        Raises:
            requests.RequestException: If the HTTP request fails.
        """
        r = self.session.get(self.url, timeout=10)
        r.raise_for_status()
        updates = []

        soup = BeautifulSoup(r.text, "html.parser")

        # Find all article blocks (class="block ..." for live blog updates)
        articles = soup.find_all("article", {"class": re.compile(r"\bblock\b")})

        if not articles:
            logger.warning(
                f"No article blocks found on {self.url}; "
                "Guardian markup may have changed",
            )

        for article in reversed(articles):  # Reverse to get oldest-first
            try:
                # Extract heading from <h2> inside <header>
                heading = ""
                header = article.find("header")
                if header:
                    h2 = header.find("h2")
                    if h2:
                        heading = h2.get_text(strip=True)

                # Extract all paragraph text (any <p> tag — Guardian hashes the classes,
                # so we can't rely on class matching; instead grab any paragraph in the article)
                paragraphs = article.find_all("p")
                body = " ".join([p.get_text(strip=True) for p in paragraphs])

                if heading and body:
                    full_text = f"{heading} {body}"
                elif heading:
                    full_text = heading
                else:
                    full_text = body

                # Clean the text
                text = self._clean_text(full_text)

                # Filter: minimum length only
                if len(text) >= MIN_UPDATE_LENGTH and text not in updates:
                    updates.append(text)

            except (AttributeError, TypeError) as e:
                logger.debug(f"Error extracting article: {e}")
                continue

        return updates

    def fetch(self) -> list[str]:
        """Poll the live blog and return newly discovered updates."""
        try:
            current = self._extract_all_updates()

            if not current:
                return []

            current = list(dict.fromkeys(current))

            # Build set of all logged text for deduplication
            logged = set()
            for batch in self.feed:
                if isinstance(batch, dict) and "updates" in batch:
                    for upd in batch.get("updates", []):
                        logged.add(upd)

            new_updates = [u for u in current if u not in logged]

            if new_updates:
                self.feed.append(
                    {
                        "fetched_at": datetime.now().isoformat(),
                        "count": len(new_updates),
                        "updates": new_updates,
                    },
                )
                self._save()

            return new_updates

        except requests.RequestException as e:
            logger.error(f"Network error: {e}")
            return []
        except OSError as e:
            logger.error(f"File error: {e}")
            return []

    def display(self) -> None:
        """Print all cached updates with ANSI colour highlights."""
        print("\n" + "=" * 80)
        print("🏏 GUARDIAN CRICKET LIVE FEED".center(80))
        print(f"Last updated: {datetime.now().isoformat()}".center(80))
        print("=" * 80)

        if not self.feed:
            print("\nNo updates yet.\n")
            return

        all_updates = []
        for batch in self.feed:
            if isinstance(batch, dict) and "updates" in batch:
                all_updates.extend(batch.get("updates", []))

        print(f"\n📊 Total updates: {len(all_updates)}\n")

        for upd in all_updates[-DISPLAY_LIMIT:]:
            colourised = self._colourise_text(upd)
            print(colourised)
            print("-" * 80)

        print("=" * 80 + "\n")

    def watch(self, interval: int = DEFAULT_INTERVAL, max_runtime_hours: int = 9) -> None:
        """Poll the live blog repeatedly and print new updates.

        Args:
            interval: Polling interval in seconds (default: 120).
            max_runtime_hours: Maximum runtime in hours before auto-stopping (default: 9).
        """
        max_runtime_seconds = max_runtime_hours * 3600
        start_time = time()

        # Calculate wall-clock end time
        end_time = datetime.now() + timedelta(hours=max_runtime_hours)
        end_time_str = end_time.strftime("%H:%M")

        msg = (
            f"Starting watch mode (polling every {interval}s, "
            f"will stop after {max_runtime_hours}h at {end_time_str})"
        )
        print(msg)
        logger.info(msg)
        try:
            while True:
                try:
                    new_updates = self.fetch()
                except Exception as e:
                    logger.error(
                        f"Unexpected error during fetch; will retry next interval: {e}",
                        exc_info=True,
                    )
                    new_updates = []

                # Print only the new updates returned by fetch()
                for update in new_updates:
                    colourised = self._colourise_text(update)
                    print(colourised)
                    print("-" * 80)

                # Check timeout before sleeping
                elapsed = time() - start_time
                if elapsed > max_runtime_seconds:
                    print(f"\n\nTimeout: {max_runtime_hours}h runtime reached, stopping.")
                    logger.info(f"Watch mode timeout after {elapsed / 3600:.1f} hours")
                    return

                remaining = max_runtime_seconds - (time() - start_time)
                sleep_time = interval if remaining > interval else remaining
                if sleep_time > 0:
                    sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n\nStopped.")
            logger.info("Watch mode stopped by user")


def main() -> None:
    """Parse arguments and run the tracker."""
    parser = argparse.ArgumentParser(
        description="Follow a Guardian cricket live blog and stream over-by-over updates.",
    )
    parser.add_argument("url", help="URL of the Guardian live blog page")
    parser.add_argument(
        "command",
        choices=["fetch", "watch", "log"],
        help="fetch: poll once and display; watch: poll repeatedly; log: dump JSON log",
    )
    parser.add_argument(
        "interval",
        type=int,
        nargs="?",
        default=DEFAULT_INTERVAL,
        help="Polling interval in seconds for watch mode (default: 120)",
    )
    parser.add_argument(
        "--max-hours",
        type=int,
        default=9,
        help="Maximum watch runtime in hours before auto-stopping (default: 9)",
    )
    args = parser.parse_args()

    tracker = CricketFeedTracker(args.url)
    if args.command == "fetch":
        tracker.fetch()
        tracker.display()
    elif args.command == "watch":
        tracker.watch(args.interval, max_runtime_hours=args.max_hours)
    else:  # log
        print(json.dumps(tracker.feed, indent=2))


if __name__ == "__main__":
    main()
