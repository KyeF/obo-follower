#!/usr/bin/env python3
import requests, hashlib, json, sys, re
from pathlib import Path
from datetime import datetime
from time import sleep

class CricketFeedTracker:
    def __init__(self, url):
        self.url = url
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        self.log_path  = Path.home()/f".cricket-feed-{h}.json"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent":"Mozilla/5.0"})
        self._load()

    def _load(self):
        if self.log_path.exists():
            self.feed = json.load(self.log_path.open())
        else:
            self.feed = []

    def _save(self):
        self.log_path.write_text(json.dumps(self.feed, indent=2))

    def _clean_text(self, text):
        """Clean up extracted text"""
        text = text.replace('double quotation mark', '"')
        text = text.replace('&quot;', '"')
        text = text.replace('&amp;', '&')
        text = text.replace('View image in fullscreen', '')
        text = text.replace('Photograph:', 'Photo:')
        text = text.replace('Share Updated at', '')
        text = text.replace('Share', '')
        text = re.sub(r'^(\d+h ago\s+\d+\.\d+\s+BST\s+)', '', text)

        return text

    def _extract_all_updates(self):
        """Extract updates from JSON-LD structured data"""
        r = self.session.get(self.url, timeout=10)
        r.raise_for_status()
        updates = []

        json_ld_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
        matches = re.findall(json_ld_pattern, r.text, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match)
                items = [data] if isinstance(data, dict) else data

                for item in items:
                    if not isinstance(item, dict) or item.get("@type") != "LiveBlogPosting":
                        continue

                    main_headline = item.get("headline", "")
                    updates_data = item.get("liveBlogUpdate", [])

                    # Reverse so oldest comes first
                    updates_data = list(reversed(updates_data))

                    for update in updates_data:
                        body = update.get("articleBody", "")

                        # Remove main headline if present
                        if body.startswith(main_headline):
                            body = body[len(main_headline):].strip()

                        # Clean the text
                        text = self._clean_text(body)

                        # Filter
                        if len(text) >= 40 and text not in updates:
                            updates.append(text)

            except (json.JSONDecodeError, TypeError):
                continue

        return updates

    def fetch(self):
        try:
            current = self._extract_all_updates()

            if not current:
                print("❌ No updates extracted", file=sys.stderr)
                return []

            logged = set()
            for batch in self.feed:
                for upd in batch["updates"]:
                    logged.add(upd)

            new_updates = [u for u in current if u not in logged]

            if new_updates:
                self.feed.append({
                    "fetched_at": datetime.now().isoformat(),
                    "count": len(new_updates),
                    "updates": new_updates
                })
                self._save()
                return new_updates
            else:
                return []

        except Exception as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            return []

    def display(self):
        print("\n" + "="*80)
        print("🏏 GUARDIAN CRICKET LIVE FEED".center(80))
        print("="*80)

        if not self.feed:
            print("\nNo updates yet.\n")
            return

        all_updates = []
        for batch in self.feed:
            all_updates.extend(batch["updates"])

        print(f"\n📊 Total updates: {len(all_updates)}\n")

        for upd in all_updates[-30:]:
            print(upd)
            print()

        print("="*80 + "\n")

    def watch(self, interval=120):
        print(f"\n🔍 Watching every {interval}s (Ctrl+C to stop)\n")
        shown_count = 0

        try:
            while True:
                new_updates = self.fetch()

                # Get total updates
                all_updates = []
                for batch in self.feed:
                    all_updates.extend(batch["updates"])

                # Display NEW ones since last check
                new_count = len(all_updates)
                if new_count > shown_count:
                    for upd in all_updates[shown_count:]:
                        print(upd)
                        print("\n" + "-" * 80 + "\n")
                    shown_count = new_count

                sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 Stopped.")

if __name__=="__main__":
    if len(sys.argv)<3:
        print("Usage: obo-follower.py <url> <watch|fetch|log> [interval]")
        sys.exit(1)

    url, cmd = sys.argv[1], sys.argv[2]
    interval = int(sys.argv[3]) if len(sys.argv)>3 else 120
    t = CricketFeedTracker(url)

    if cmd=="fetch":
        t.fetch(); t.display()
    elif cmd=="watch":
        t.watch(interval)
    elif cmd=="log":
        print(json.dumps(t.feed, indent=2))
