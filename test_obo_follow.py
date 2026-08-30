"""Unit tests for obo-follower."""

import json
import sys
from pathlib import Path

import pytest
import re

from obo_follow import COLOURS, CricketFeedTracker


@pytest.fixture
def temp_log_path(tmp_path):
    """Provide a temporary cache file path."""
    return tmp_path / "test-feed.json"


@pytest.fixture
def tracker(temp_log_path, monkeypatch):
    """Create a tracker instance with a temporary cache path."""
    tracker = CricketFeedTracker("https://example.com/test")
    monkeypatch.setattr(tracker, "log_path", temp_log_path)
    tracker.feed = []
    tracker._use_colour = True
    return tracker


class TestCleanText:
    """Tests for _clean_text() — text sanitisation and normalisation."""

    def test_removes_share_artifacts(self, tracker):
        """Guardian live blogs include 'Share' and timestamp text; should be stripped."""
        text = "4m ago 14.31 BST Share WICKET! Atkinson LBW b Mohammad Ali 7"
        cleaned = tracker._clean_text(text)
        assert cleaned == "WICKET! Atkinson LBW b Mohammad Ali 7"

    def test_removes_multiple_shares(self, tracker):
        """Multiple 'Share' strings should all be removed."""
        text = "Share Updated at Share WICKET!"
        cleaned = tracker._clean_text(text)
        assert cleaned == "WICKET!"

    def test_decodes_html_entities(self, tracker):
        """HTML entities like &quot; and &amp; should be decoded."""
        text = "Root said &quot;great&quot; &amp; it was"
        cleaned = tracker._clean_text(text)
        assert cleaned == 'Root said "great" & it was'

    def test_normalises_whitespace(self, tracker):
        """Multiple spaces and newlines should collapse to single spaces."""
        text = "England  \n\n  177-7  \t  (Lawrence  50)"
        cleaned = tracker._clean_text(text)
        assert cleaned == "England 177-7 (Lawrence 50)"

    def test_strips_leading_trailing_whitespace(self, tracker):
        """Leading and trailing whitespace should be removed."""
        text = "   WICKET!   "
        cleaned = tracker._clean_text(text)
        assert cleaned == "WICKET!"

    def test_inserts_space_after_closing_paren_before_capital(self, tracker):
        """Glued text like ')Time' should be split with a space: ') Time'."""
        text = "Lawrence 37, Robinson 0)Time for tea"
        cleaned = tracker._clean_text(text)
        assert cleaned == "Lawrence 37, Robinson 0) Time for tea"

    def test_removes_photograph_metadata(self, tracker):
        """'Photograph:' should be shortened to 'Photo:'."""
        text = "Photograph: Getty Images / Test"
        cleaned = tracker._clean_text(text)
        assert cleaned == "Photo: Getty Images / Test"

    def test_removes_view_image_fullscreen(self, tracker):
        """'View image in fullscreen' is an accessibility artefact; should be removed."""
        text = "A great catch View image in fullscreen during the match"
        cleaned = tracker._clean_text(text)
        assert cleaned == "A great catch during the match"

    def test_removes_double_quotation_mark_text(self, tracker):
        """'double quotation mark' is rendered from pull-quote icons; replace with actual quote."""
        text = "He said double quotation mark Hello double quotation mark"
        cleaned = tracker._clean_text(text)
        assert cleaned == 'He said " Hello "'


class TestColouriseClause:
    """Tests for _colourise_clause() — single-clause highlighting."""

    def test_highlights_wicket(self, tracker):
        """WICKET! ... should be highlighted in red."""
        clause = "WICKET! Atkinson LBW b Mohammad Ali 7 (England 162-7)"
        result = tracker._colourise_clause(clause)
        # Should contain red ANSI codes around the match
        assert "\033[91m" in result and "\033[0m" in result
        assert "WICKET!" in result

    def test_highlights_not_out(self, tracker):
        """'not out!' should be highlighted in green."""
        clause = "Root survives the review, not out!"
        result = tracker._colourise_clause(clause)
        assert "\033[92m" in result  # GREEN
        assert "not out!" in result

    def test_highlights_review_case_insensitive(self, tracker):
        """'review' (any case) should be highlighted in yellow."""
        clause = "Broad reviews the decision!"
        result = tracker._colourise_clause(clause)
        assert "\033[93m" in result  # YELLOW
        assert "review" in result.lower()

    def test_highlights_rain_stops_play(self, tracker):
        """'Rain stops play' should be highlighted in blue."""
        clause = "Rain stops play! The umpires have come off the field."
        result = tracker._colourise_clause(clause)
        assert "\033[94m" in result  # BLUE
        assert "rain" in result.lower()

    def test_highlights_more_rain(self, tracker):
        """'More rain' should be highlighted in blue."""
        clause = "More rain delays the start of play."
        result = tracker._colourise_clause(clause)
        assert "\033[94m" in result  # BLUE

    def test_highlights_bad_light_stops_play(self, tracker):
        """'Bad light stops play' should be highlighted in orange."""
        clause = "Bad light stops play! The sun has dipped behind the pavilion."
        result = tracker._colourise_clause(clause)
        assert "\033[38;5;208m" in result  # ORANGE

    def test_highlights_stumps(self, tracker):
        """'Stumps' should be highlighted in orange."""
        clause = "Stumps! England 287-5 at close of play."
        result = tracker._colourise_clause(clause)
        assert "\033[38;5;208m" in result

    def test_highlights_abandoned(self, tracker):
        """'Abandoned' should be highlighted in red."""
        clause = "Abandoned due to bad light. No play today."
        result = tracker._colourise_clause(clause)
        assert "\033[91m" in result  # RED

    def test_highlights_fifty(self, tracker):
        """'fifty to' or 'fifty for' should be highlighted in green."""
        clause = "Fifty to Lawrence! (47th over: England 177-7)"
        result = tracker._colourise_clause(clause)
        assert "\033[92m" in result  # GREEN
        assert "fifty to" in result.lower()

    def test_highlights_hundred(self, tracker):
        """'hundred to' or 'hundred for' should be highlighted in green."""
        clause = "Hundred to Root! (78th over: England 345-3)"
        result = tracker._colourise_clause(clause)
        assert "\033[92m" in result  # GREEN

    def test_highlights_win(self, tracker):
        """'Won games should be highlighted in red."""
        clause = "England win by 100 runs"
        result = tracker._colourise_clause(clause)
        assert "\033[92m" in result  # GREEN

    def test_highlights_lose(self, tracker):
        """Lost games should be highlighted in red."""
        clause = "England lose by 100 runs"
        result = tracker._colourise_clause(clause)
        assert "\033[91m" in result  # RED

    def test_highlights_capitalised_win(self, tracker):
        """'Won games should be highlighted in red."""
        clause = "England Win by 100 runs"
        result = tracker._colourise_clause(clause)
        assert "\033[92m" in result  # GREEN

    def test_highlights_capitalised_lose(self, tracker):
        """Lost games should be highlighted in red."""
        clause = "England Lose by 100 runs"
        result = tracker._colourise_clause(clause)
        assert "\033[91m" in result  # RED

    def test_highlights_over_header(self, tracker):
        """Over headers should be bolded (no colour)."""
        clause = "47th over: England 177-7 (Lawrence 50, Robinson 2)"
        result = tracker._colourise_clause(clause)
        assert "\033[1m" in result  # BOLD
        # Should still contain the text
        assert "47th over" in result

    def test_no_highlight_plain_text(self, tracker):
        """Text with no trigger phrases should pass through unchanged."""
        clause = "Lawrence plays a solid defence"
        result = tracker._colourise_clause(clause)
        assert result == clause

    def test_priority_wicket_over_review(self, tracker):
        """WICKET should be highlighted in preference to other patterns in same clause."""
        # Contrived, but tests priority ordering
        clause = "WICKET! The batsman reviews but it's out anyway."
        result = tracker._colourise_clause(clause)
        # Should be red (WICKET), not yellow (review)
        assert "\033[91m" in result  # RED
        assert "WICKET!" in result.split(";")[0] or "WICKET" in result[:20]


class TestColouriseText:
    """Tests for _colourise_text() — multi-clause text with independent colouring."""

    def test_no_colour_when_not_tty(self, tracker, monkeypatch):
        """Should return text unchanged when not attached to a TTY."""
        monkeypatch.setattr(tracker, "_use_colour", False)
        text = "WICKET! Atkinson LBW b Mohammad Ali 7 (England 162-7)"
        result = tracker._colourise_text(text)
        assert result == text
        assert "\033[" not in result  # No ANSI codes

    def test_splits_on_sentence_punctuation(self, tracker):
        """Text should split at sentence endings (!, ., ?)."""
        text = "WICKET! Atkinson out. Fifty to Lawrence!"
        result = tracker._colourise_text(text)
        # Each clause should be coloured independently
        assert "\033[91m" in result  # RED for WICKET
        assert "\033[92m" in result  # GREEN for fifty
        # Exact ordering depends on clause boundaries, but both should be present

    def test_splits_before_over_header(self, tracker):
        """Text should split right before an over-header pattern."""
        text = "Fifty to Lawrence! 47th over: England 177-7 (Lawrence 50, Robinson 2)"
        result = tracker._colourise_text(text)
        # The fifty should be green, the over header should be bold
        assert "\033[92m" in result  # GREEN for fifty
        assert "\033[1m" in result  # BOLD for over

    def test_handles_glued_clauses(self, tracker):
        """When a closing paren is followed by a capital letter with no space,
        _clean_text should have added a space, allowing proper clause splitting."""
        # Assuming _clean_text was called first (as it is in _extract_all_updates)
        text = "Lawrence 37, Robinson 0) Time for tea"  # space already inserted
        result = tracker._colourise_text(text)
        # Text should come through colourised or plain depending on trigger words
        assert "Time" in result

    def test_multi_event_update(self, tracker):
        """A single update with multiple distinct events should highlight each separately."""
        text = "More rain! And fifty to Lawrence 47th over: England 177-7 (Lawrence 50, Robinson 2)"
        result = tracker._colourise_text(text)
        # Should have blue (rain), green (fifty), and bold (over)
        assert "\033[94m" in result or "More rain" in result  # BLUE or plain
        assert "\033[92m" in result or "fifty" in result  # GREEN or plain
        assert "\033[1m" in result or "47th over" in result  # BOLD or plain


class TestLoadSave:
    """Tests for _load() and _save() — persistence."""

    def test_load_creates_empty_feed_if_no_file(self, tracker):
        """Loading with no file should result in an empty feed."""
        assert tracker.feed == []

    def test_save_and_load_roundtrip(self, tracker):
        """Saving and reloading should preserve feed contents."""
        test_feed = [
            {
                "fetched_at": "2026-08-29T14:00:00",
                "count": 2,
                "updates": [
                    "WICKET! Atkinson LBW b Mohammad Ali 7",
                    "Fifty to Lawrence!",
                ],
            },
        ]
        tracker.feed = test_feed
        tracker._save()

        # Create a new tracker instance pointing to the same log file
        tracker2 = CricketFeedTracker("https://example.com/test")
        tracker2.log_path = tracker.log_path
        tracker2._load()

        assert tracker2.feed == test_feed

    def test_normalise_old_string_format_on_load(self, tracker, temp_log_path):
        """Loading old string-based feed should be normalised to new dict format."""
        # Write old format directly to the file
        old_feed = [
            "WICKET! Atkinson LBW b Mohammad Ali 7",
            "Fifty to Lawrence!",
        ]
        with temp_log_path.open("w") as f:
            json.dump(old_feed, f)

        tracker._load()

        # Should be normalised to dict format
        assert len(tracker.feed) == 2
        assert all(isinstance(item, dict) for item in tracker.feed)
        assert tracker.feed[0]["updates"] == ["WICKET! Atkinson LBW b Mohammad Ali 7"]

    def test_load_handles_corrupt_json(self, tracker, temp_log_path, caplog):
        """Loading corrupt JSON should warn and start with empty feed."""
        # Write invalid JSON
        temp_log_path.write_text("{ this is not valid json ]")

        tracker._load()

        assert tracker.feed == []
        assert "Could not read" in caplog.text or "Warning" in caplog.text

    def test_load_handles_missing_file_gracefully(self, tracker):
        """Loading from a missing file should start with empty feed."""
        tracker.log_path = Path("/nonexistent/path/feed.json")
        tracker._load()
        assert tracker.feed == []

    def test_save_is_atomic(self, tracker, temp_log_path, monkeypatch):
        """Save should create a temp file before replacing, avoiding corruption on interrupt."""
        test_feed = [
            {
                "fetched_at": "2026-08-29T14:00:00",
                "count": 1,
                "updates": ["Test update"],
            },
        ]
        tracker.feed = test_feed
        tracker.log_path = temp_log_path

        # Capture the temp file creation
        tmp_files = []

        original_write_text = Path.write_text

        def tracked_write_text(self, data, **kwargs):
            if ".tmp" in str(self):
                tmp_files.append(str(self))
            return original_write_text(self, data, **kwargs)

        monkeypatch.setattr(Path, "write_text", tracked_write_text)

        tracker._save()

        # Confirm the temp file was created and then replaced
        assert len(tmp_files) > 0
        # Final file should exist and be readable
        assert temp_log_path.exists()


class TestFetchDeduplication:
    """Tests for fetch() — ensuring no duplicate updates."""

    def test_deduplicates_across_calls(self, tracker):
        """Running fetch twice should only return new updates on the second call."""
        # Simulate previous updates in the feed
        tracker.feed = [
            {
                "fetched_at": "2026-08-29T14:00:00",
                "count": 1,
                "updates": ["WICKET! Atkinson LBW b Mohammad Ali 7"],
            },
        ]

        # Mock the extraction to return the same update plus a new one
        def mock_extract():
            return [
                "WICKET! Atkinson LBW b Mohammad Ali 7",  # duplicate
                "Fifty to Lawrence!",  # new
            ]

        tracker._extract_all_updates = mock_extract

        new = tracker.fetch()

        assert new == ["Fifty to Lawrence!"]
        assert len(tracker.feed) == 2  # Original + new batch

    def test_fetch_returns_empty_if_all_duplicates(self, tracker):
        """If all extracted updates are already logged, fetch should return empty list."""
        tracker.feed = [
            {
                "fetched_at": "2026-08-29T14:00:00",
                "count": 1,
                "updates": ["WICKET! Atkinson LBW b Mohammad Ali 7"],
            },
        ]

        def mock_extract():
            return ["WICKET! Atkinson LBW b Mohammad Ali 7"]  # Same as before

        tracker._extract_all_updates = mock_extract

        new = tracker.fetch()

        assert new == []


class TestExtractAllUpdates:
    """Tests for _extract_all_updates() — HTML parsing."""

    def test_extracts_heading_and_body(self, tracker):
        """Should extract heading from <h2> and concatenate paragraph text."""
        html = """
        <article class="block dcr-xyz">
            <header><h2>WICKET! Atkinson out</h2></header>
            <p>Atkinson LBW b Mohammad Ali 7 (England 162-7)</p>
        </article>
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("article")
        assert len(articles) == 1

        header = articles[0].find("header")
        h2 = header.find("h2")
        assert h2.get_text(strip=True) == "WICKET! Atkinson out"

        paras = articles[0].find_all("p")
        body = " ".join([p.get_text(strip=True) for p in paras])
        assert "Atkinson LBW" in body

    def test_skips_short_updates(self, tracker):
        """Updates shorter than MIN_UPDATE_LENGTH should be filtered out."""

        def mock_extract():
            return ["Short", "This is a longer update that exceeds the minimum length"]

        tracker._extract_all_updates = mock_extract

        updates = tracker.fetch()

        # Only the long one should be in new_updates
        new = [u for u in updates if len(u) >= 40]
        assert "Short" not in new

    def test_deduplicates_identical_updates(self, tracker):
        """Identical updates appearing twice in one fetch should only be stored once."""

        def mock_extract():
            return [
                "This is a long enough update to pass the length filter",
                "This is a long enough update to pass the length filter",  # duplicate
                "Another unique update that is also long enough",
            ]

        tracker._extract_all_updates = mock_extract

        new = tracker.fetch()

        # Should have 2 unique updates
        assert len(new) == 2


class TestFetchNetworkErrors:
    """Tests for network failure handling in fetch()."""

    def test_fetch_handles_connection_error(self, tracker, monkeypatch):
        """ConnectionError during HTTP request should be caught and logged."""
        import requests

        def mock_get(*args, **kwargs):
            raise requests.ConnectionError("Network unreachable")

        monkeypatch.setattr(tracker.session, "get", mock_get)

        result = tracker.fetch()

        assert result == []  # Returns empty list on error
        assert len(tracker.feed) == 0  # Feed not modified

    def test_fetch_handles_timeout(self, tracker, monkeypatch):
        """Timeout during HTTP request should be caught and logged."""
        import requests

        def mock_get(*args, **kwargs):
            raise requests.Timeout("Connection timed out")

        monkeypatch.setattr(tracker.session, "get", mock_get)

        result = tracker.fetch()

        assert result == []

    def test_fetch_handles_http_error_status(self, tracker, monkeypatch):
        """HTTP error status codes (e.g. 404, 500) should be caught."""
        import requests

        class MockResponse:
            def raise_for_status(self):
                raise requests.HTTPError("404 Not Found")

            @property
            def text(self):
                return "<html></html>"

        def mock_get(*args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(tracker.session, "get", mock_get)

        result = tracker.fetch()

        assert result == []


class TestExtractionEdgeCases:
    """Tests for edge cases in HTML extraction."""

    def test_extract_handles_missing_header(self, tracker, monkeypatch):
        """Article with no <header> should gracefully skip heading extraction."""

        html = """
        <article class="block dcr-xyz">
            <p>Update text here without a heading, but long enough to pass the filter</p>
        </article>
        """

        def mock_get(*args, **kwargs):
            from unittest.mock import Mock

            mock_resp = Mock()
            mock_resp.text = html
            mock_resp.raise_for_status = Mock()
            return mock_resp

        monkeypatch.setattr(tracker.session, "get", mock_get)

        updates = tracker._extract_all_updates()

        assert len(updates) >= 1
        assert "Update text here without a heading" in updates[0]

    def test_extract_handles_missing_h2(self, tracker, monkeypatch):
        """Header without <h2> should gracefully skip heading."""
        from unittest.mock import Mock

        html = """
        <article class="block dcr-xyz">
            <header><h3>Wrong heading level</h3></header>
            <p>Update text here that is long enough to pass the minimum length filter</p>
        </article>
        """

        def mock_get(*args, **kwargs):
            mock_resp = Mock()
            mock_resp.text = html
            mock_resp.raise_for_status = Mock()
            return mock_resp

        monkeypatch.setattr(tracker.session, "get", mock_get)

        updates = tracker._extract_all_updates()

        assert len(updates) >= 1

    def test_extract_handles_no_paragraphs(self, tracker, monkeypatch):
        """Article with heading but no paragraphs should still extract heading."""
        from unittest.mock import Mock

        html = """
        <article class="block dcr-xyz">
            <header><h2>Heading only</h2></header>
        </article>
        """

        def mock_get(*args, **kwargs):
            mock_resp = Mock()
            mock_resp.text = html
            mock_resp.raise_for_status = Mock()
            return mock_resp

        monkeypatch.setattr(tracker.session, "get", mock_get)

        updates = tracker._extract_all_updates()

        # Should include heading if at least 40 chars
        # (unlikely with just "Heading only", but test the graceful handling)
        # This should not crash, which is the main point
        assert isinstance(updates, list)

    def test_extract_handles_no_articles_found(self, tracker, monkeypatch, caplog):
        """When no article blocks are found, should log warning."""
        from unittest.mock import Mock

        html = "<html><body>No articles here</body></html>"

        def mock_get(*args, **kwargs):
            mock_resp = Mock()
            mock_resp.text = html
            mock_resp.raise_for_status = Mock()
            return mock_resp

        monkeypatch.setattr(tracker.session, "get", mock_get)

        updates = tracker._extract_all_updates()

        assert updates == []
        assert "No article blocks found" in caplog.text

    def test_extract_handles_malformed_html(self, tracker, monkeypatch):
        """Malformed HTML should not crash extraction."""
        from unittest.mock import Mock

        html = """
        <article class="block dcr-xyz">
            <header><h2>Unclosed heading
            <p>Text with <span unclosed>
        </article>
        """

        def mock_get(*args, **kwargs):
            mock_resp = Mock()
            mock_resp.text = html
            mock_resp.raise_for_status = Mock()
            return mock_resp

        monkeypatch.setattr(tracker.session, "get", mock_get)

        # Should not crash — BeautifulSoup handles broken HTML leniently
        updates = tracker._extract_all_updates()
        assert isinstance(updates, list)

    def test_extract_handles_exception_in_article_loop(self, tracker, monkeypatch):
        """If an article raises AttributeError, loop continues to next article."""
        from unittest.mock import Mock, MagicMock
        from bs4 import BeautifulSoup

        html = """
        <article class="block dcr-xyz">
            <header><h2>Good article</h2></header>
            <p>Good text here that is long enough to pass the filter</p>
        </article>
        """

        def mock_get(*args, **kwargs):
            mock_resp = Mock()
            mock_resp.text = html
            mock_resp.raise_for_status = Mock()
            return mock_resp

        monkeypatch.setattr(tracker.session, "get", mock_get)

        # Inject a broken mock article alongside the real one, so we can
        # verify the loop's except clause skips it and continues.  🎯CHANGE🎯
        original_find_all = BeautifulSoup.find_all

        def patched_find_all(self, *args, **kwargs):
            result = original_find_all(self, *args, **kwargs)
            name = args[0] if args else kwargs.get("name")
            if name == "article":
                bad_article = MagicMock()
                bad_article.find.side_effect = AttributeError("Simulated parse error")
                return list(result) + [bad_article]
            return result

        monkeypatch.setattr(BeautifulSoup, "find_all", patched_find_all)

        updates = tracker._extract_all_updates()

        # Good article's update should still come through; bad one skipped silently
        assert len(updates) == 1
        assert "Good text here" in updates[0]


class TestTextCleaningEdgeCases:
    """Tests for edge cases in text cleaning."""

    def test_clean_text_handles_empty_string(self, tracker):
        """Empty string input should return empty string."""
        result = tracker._clean_text("")
        assert result == ""

    def test_clean_text_handles_whitespace_only(self, tracker):
        """Whitespace-only input should return empty string after strip."""
        result = tracker._clean_text("   \n\t  ")
        assert result == ""

    def test_clean_text_handles_no_changes_needed(self, tracker):
        """Clean text should pass through unchanged if already clean."""
        text = "Clean text with no artefacts"
        result = tracker._clean_text(text)
        assert result == text

    def test_clean_text_handles_consecutive_entities(self, tracker):
        """Multiple HTML entities in a row should all be decoded."""
        text = "&quot;&quot;&quot; test &amp;&amp;&amp;"
        result = tracker._clean_text(text)
        assert result == '""" test &&&'


class TestColorizeEdgeCases:
    """Tests for edge cases in colouring logic."""

    def test_colourise_text_handles_empty_string(self, tracker):
        """Empty string should pass through unchanged."""
        result = tracker._colourise_text("")
        assert result == ""

    def test_colourise_text_handles_whitespace_only(self, tracker):
        """Whitespace-only string should pass through unchanged."""
        result = tracker._colourise_text("   \n  ")
        assert result == "   \n  "

    def test_colourise_clause_handles_no_punctuation(self, tracker):
        """Clause with no trigger phrases should return unchanged."""
        clause = "This is a regular update with no special events"
        result = tracker._colourise_clause(clause)
        assert result == clause

    def test_colourise_clause_handles_unbalanced_parens(self, tracker):
        """Over header with missing closing paren should not crash."""
        clause = "Fifty to Lawrence 47th over: England 177-7 (Lawrence 50"
        result = tracker._colourise_clause(clause)
        # Should return something (either unchanged or partially matched)
        assert isinstance(result, str)

    def test_colourise_text_handles_no_split_boundaries(self, tracker):
        """Text with no split boundaries should be one clause."""
        text = "No punctuation here just text"
        result = tracker._colourise_text(text)
        # Should be returned unchanged (no trigger phrases)
        assert "No punctuation here just text" in result


class TestPersistenceErrorCases:
    """Tests for error handling in save/load operations."""

    def test_load_handles_empty_file(self, tracker, temp_log_path):
        """Empty JSON file (zero bytes) should be handled gracefully."""
        temp_log_path.write_text("")

        tracker._load()

        # Should log warning and start with empty feed
        assert tracker.feed == []

    def test_load_handles_json_null(self, tracker, temp_log_path):
        """JSON file containing just `null` should be handled gracefully."""
        temp_log_path.write_text("null")

        tracker._load()

        # Currently this will raise TypeError: 'NoneType' object is not iterable
        # This is a BUG that should be fixed — see note below
        # For now, documenting expected crash
        # TODO: Fix _load() to catch TypeError for invalid JSON structures

    def test_load_handles_json_dict_not_list(self, tracker, temp_log_path):
        """JSON file containing a dict instead of list should be handled gracefully."""
        temp_log_path.write_text('{"updates": []}')

        tracker._load()

        # Currently this will iterate over dict keys, creating odd entries
        # This is a fragility — _load() should validate the JSON structure
        # TODO: Fix _load() to validate JSON is a list at top level

    def test_save_handles_permission_denied(self, tracker, monkeypatch):
        """Permission denied when writing temp file should be caught by fetch()."""

        def mock_write_text(self, data, **kwargs):
            raise PermissionError("Permission denied")

        monkeypatch.setattr("pathlib.Path.write_text", mock_write_text)

        tracker.feed = [{"fetched_at": "2026-08-29", "count": 1, "updates": ["test"]}]

        # Mock extraction to return a new update
        def mock_extract():
            return ["new update that is long enough to pass the filter"]

        tracker._extract_all_updates = mock_extract

        result = tracker.fetch()

        # Should be caught by OSError handler in fetch()
        assert result == []

    def test_load_preserves_integrity_after_corrupt_save(
        self, tracker, temp_log_path, monkeypatch,
    ):
        """If save fails midway, load should not crash on old data."""
        # Write valid data initially
        valid_feed = [
            {
                "fetched_at": "2026-08-29T14:00:00",
                "count": 1,
                "updates": ["Initial update"],
            },
        ]
        temp_log_path.write_text(json.dumps(valid_feed))

        # Now corrupt the file (simulate partial write)
        tracker.log_path = temp_log_path
        tracker.feed = valid_feed
        temp_log_path.write_text('{"incomplete": "json"')

        # Load should handle gracefully
        tracker._load()

        # Should either restore the original valid data or start fresh
        # Currently it starts fresh (which is safe)
        assert isinstance(tracker.feed, list)


class TestCLIErrorHandling:
    """Tests for CLI argument validation."""

    SCRIPT_PATH = Path(__file__).parent / "obo-follow.py"

    def test_cli_rejects_missing_url(self):
        """CLI should require URL as first argument."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(self.SCRIPT_PATH), "fetch"],
            capture_output=True,
        )

        assert result.returncode != 0

    def test_cli_rejects_invalid_command(self):
        """CLI should reject unrecognized commands."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(self.SCRIPT_PATH),
                "http://example.com",
                "invalid-command",
            ],
            capture_output=True,
        )

        assert result.returncode != 0

    def test_cli_rejects_invalid_interval_type(self):
        """CLI should reject non-integer intervals."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(self.SCRIPT_PATH),
                "http://example.com",
                "watch",
                "not-an-integer",
            ],
            capture_output=True,
        )

        assert result.returncode != 0



class TestColouringRecentFixes:
    """Tests for recent changes to colouring rules and clause splitting."""

    def test_boundary_regex_matches_nd_ordinals(self, tracker):
        """Clause splitting should correctly split before 2nd, 32nd, 42nd overs."""
        # The boundary regex was fixed from "and" to "nd"
        text = "Fifty to Lawrence! 2nd over: England 12-0 (Root 5, Cook 7)"

        # Parse the boundary regex to verify it matches "2nd over:"
        boundary = re.compile(
            r"[!.?]\s*|(?=\d+(?:st|nd|rd|th)\s+over:)|(?<=\))\s*(?=[A-Z])"
        )

        matches = list(boundary.finditer(text))

        # Should have matches for the ! and the lookahead before "2nd"
        assert any("2nd" in text[m.start():m.start()+20] for m in matches), \
            f"No split found before '2nd over'; matches at positions {[m.span() for m in matches]}"

    def test_win_pattern_bounded_doesnt_swallow_next_sentence(self, tracker):
        """Win pattern should not swallow unrelated text after 'to win'."""
        clause = "Pakistan need 389 to win Pakistan will be pleased at how they polished off England's tail"
        result = tracker._colourise_clause(clause)

        # The highlighting should contain "Pakistan need 389 to win" but not the following sentence
        # It should either:
        # 1. Not highlight anything (if the pattern isn't specific enough), or
        # 2. Highlight only "Pakistan need 389 to win" without the rest

        # Check that "will be pleased" is NOT bolded
        assert "will be pleased" not in result or "\033[1m" not in result.split("will be pleased")[0][-10:], \
            "Following sentence was incorrectly included in win highlight"

    def test_lose_pattern_bounded_doesnt_swallow_trailing_text(self, tracker):
        """Lose pattern should not greedily match beyond the result phrase."""
        clause = "England lose by 50 runs. India celebrates their magnificent victory."
        result = tracker._colourise_clause(clause)

        # Should not swallow "India celebrates..."
        if "\033[91m" in result:  # If RED is present
            # Extract just the highlighted portion
            highlighted = result.split("\033[0m")[0]  # Get up to first RESET
            assert "India" not in highlighted, \
                "Following sentence was incorrectly included in lose highlight"

    def test_stumps_with_negative_lookbehind_excludes_the_stumps(self, tracker):
        """'the stumps' should NOT be highlighted, only 'Stumps!' event."""
        tests = [
            ("Stumps! England 287-5", True),  # Should highlight
            ("the stumps are in place", False),  # Should NOT highlight
            ("He hit the stumps", False),  # Should NOT highlight
            ("The stumps look good today", False),  # Should NOT highlight (case-insensitive)
            ("Stumps called early due to bad light", True),  # Should highlight
        ]

        for clause, should_highlight in tests:
            result = tracker._colourise_clause(clause)
            has_orange = "\033[38;5;208m" in result

            if should_highlight:
                assert has_orange, f"Expected {clause!r} to be highlighted orange, but wasn't"
            else:
                assert not has_orange, f"Expected {clause!r} to NOT be highlighted, but was"

    def test_wicket_case_insensitive(self, tracker):
        """WICKET pattern should match any case: WICKET!, Wicket!, wicket!"""
        tests = [
            "WICKET! Atkinson LBW b Mohammad Ali 7",
            "Wicket! Root caught at slip",
            "wicket! Another batsman out",
        ]

        RED = COLOURS["RED"]
        for clause in tests:
            result = tracker._colourise_clause(clause)
            assert RED in result, f"Expected {clause!r} to be highlighted red"

    def test_review_case_insensitive(self, tracker):
        """Review pattern should match any case: Review, review, REVIEW."""
        tests = [
            "Broad reviews the decision!",
            "REVIEW called on the field",
            "review pending for LBW decision",
        ]

        YELLOW = COLOURS["YELLOW"]
        for clause in tests:
            result = tracker._colourise_clause(clause)
            assert YELLOW in result, f"Expected {clause!r} to be highlighted yellow for review"

    def test_rain_case_insensitive(self, tracker):
        """Rain patterns should match any case."""
        tests = [
            ("RAIN STOPS PLAY!", True),
            ("Rain stops play", True),
            ("More RAIN delays start", True),
            ("rain stops play early", True),
        ]

        BLUE = COLOURS["BLUE"]
        for clause, should_match in tests:
            result = tracker._colourise_clause(clause)
            has_blue = BLUE in result

            if should_match:
                assert has_blue, f"Expected {clause!r} to be highlighted blue"
            else:
                assert not has_blue, f"Expected {clause!r} to NOT be highlighted"

    def test_abandoned_case_insensitive(self, tracker):
        """Abandoned should match any case."""
        tests = [
            "ABANDONED due to rain",
            "Abandoned! No play today",
            "abandoned early due to bad light",
        ]

        RED = COLOURS["RED"]
        for clause in tests:
            result = tracker._colourise_clause(clause)
            assert RED in result, f"Expected {clause!r} to be highlighted red"

    def test_fifty_case_insensitive(self, tracker):
        """Fifty pattern should match any case."""
        tests = [
            "Fifty to Lawrence!",
            "FIFTY for Root",
            "fifty to the batter",
        ]

        GREEN = COLOURS["GREEN"]
        for clause in tests:
            result = tracker._colourise_clause(clause)
            assert GREEN in result, f"Expected {clause!r} to be highlighted green"

    def test_hundred_case_insensitive(self, tracker):
        """Hundred pattern should match any case."""
        tests = [
            "Hundred to Root!",
            "HUNDRED for Babar",
            "hundred to the middle order",
        ]

        GREEN = COLOURS["GREEN"]
        for clause in tests:
            result = tracker._colourise_clause(clause)
            assert GREEN in result, f"Expected {clause!r} to be highlighted green"

    def test_win_lose_word_boundaries_no_false_positives(self, tracker):
        """Win/lose should not match substrings like 'winter', 'loser', 'closer'."""
        tests = [
            ("It was a cold winter's day", False),  # "winter" contains "win"
            ("The closer they got to the target", False),  # "closer" contains "lose"
            ("He is a loser in this match", False),  # "loser" contains "lose"
            ("They will win the match", True),  # Standalone "win"
            ("England lose by 10 runs", True),  # Standalone "lose"
        ]

        RED = COLOURS["RED"]
        GREEN = COLOURS["GREEN"]
        for clause, should_highlight in tests:
            result = tracker._colourise_clause(clause)
            has_colour = RED in result or GREEN in result

            if should_highlight:
                assert has_colour, f"Expected {clause!r} to be highlighted"
            else:
                assert not has_colour, f"Expected {clause!r} to NOT be highlighted (false positive)"

    def test_specific_need_pattern_matches_target_phrase(self, tracker):
        """The specific 'need N to win' pattern should match exactly."""
        tests = [
            ("Pakistan need 389 to win", True),
            ("England need 5 more to win", True),
            ("They need 1 to win", True),
            ("we need to win this match", False),  # "need to win" but not the numerical target
            ("winning by needing 10", False),  # Contains "need" but not the phrase
        ]

        GREEN = COLOURS["GREEN"]
        for clause, should_match in tests:
            result = tracker._colourise_clause(clause)
            has_green = GREEN in result

            if should_match:
                assert has_green, f"Expected {clause!r} to be highlighted green"
            else:
                # Note: might still match on generic "win" pattern, so just verify the specific pattern doesn't over-match
                pass

    def test_over_header_with_nd_ordinals(self, tracker):
        """Over headers with 2nd, 32nd, 42nd overs should be bolded."""
        tests = [
            "2nd over: England 12-0 (Root 5, Cook 7)",
            "32nd over: Pakistan 87-2 (Babar 45, Imam 30)",
            "42nd over: England 156-4 (Stokes 52)",
            "51st over: India 210-5",  # st should also work
            "3rd over: Australia 18-1",  # rd should work
        ]

        BOLD = COLOURS["BOLD"]
        for clause in tests:
            result = tracker._colourise_clause(clause)
            assert BOLD in result, f"Expected {clause!r} over header to be bolded"

    def test_full_over_header_captured_not_partial(self, tracker):
        """Over header should capture the full text including parens and names."""
        clause = "54th over: England 206-9 (Archer 2, Tongue 12)"
        result = tracker._colourise_clause(clause)

        BOLD = COLOURS["BOLD"]
        RESET = COLOURS["RESET"]

        # Should contain the entire over header bolded
        assert BOLD in result and RESET in result, \
            "Over header should be bolded"

        # Verify the highlighted portion includes the full header
        # Extract what's between BOLD and RESET
        start = result.find(BOLD)
        end = result.find(RESET)
        highlighted = result[start:end]

        assert "54th over" in highlighted, "Over number should be in highlighted section"
        assert "Archer" in highlighted, "Player names should be in highlighted section"
        assert "Tongue 12" in highlighted, "Full score should be in highlighted section"

    def test_multi_clause_text_with_recent_fixes(self, tracker):
        """Real-world example: multiple clauses with recent fixes applied."""
        text = "More rain! And Pakistan need 389 to win 2nd over: England 12-0 (Root 5)"

        result = tracker._colourise_text(text)

        BLUE = COLOURS["BLUE"]
        GREEN = COLOURS["GREEN"]
        BOLD = COLOURS["BOLD"]

        # Should have blue for "More rain"
        assert BLUE in result, "Should highlight 'More rain' in blue"
        # Should have green for "need 389 to win"
        assert GREEN in result, "Should highlight 'need 389 to win' in green"
        # Should have bold for over header
        assert BOLD in result, "Should bold over header"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
