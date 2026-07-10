"""Sanity checks on the generated Xenophon build output."""

import json
import unittest
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
LINES_DIR = Path(__file__).parent.parent / "docs" / "lines"


class TestBuildOutputExists(unittest.TestCase):
    EXPECTED_FILES = [
        "plays.json",
        "chunks.json",
        "characters.json",
        "tokens.json",
        "tokens2.json",
        "tokens3.json",
        "tokens_char.json",
        "tokens_char2.json",
        "tokens_char3.json",
        "character_name_filter_config.json",
    ]

    def test_all_data_files_exist(self):
        for filename in self.EXPECTED_FILES:
            self.assertTrue((DATA_DIR / filename).exists(), f"{filename} must exist")

    def test_no_commentary_data_ships(self):
        self.assertFalse((DATA_DIR / "commentary_interest.json").exists())

    def test_lines_file_exists(self):
        self.assertTrue((LINES_DIR / "all_lines.json").exists(), "all_lines.json must exist")


class TestWorks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.works = json.loads((DATA_DIR / "plays.json").read_text())

    def test_has_14_works(self):
        self.assertEqual(len(self.works), 14)

    def test_work_has_required_fields(self):
        required = {
            "play_id",
            "location",
            "title",
            "abbr",
            "genre",
            "first_performance_year",
            "total_words",
            "total_lines",
            "num_acts",
            "num_scenes",
            "mattr_50",
        }
        for work in self.works:
            self.assertTrue(required.issubset(work.keys()), f"Missing fields for {work.get('title')}")
            self.assertEqual(work["num_scenes"], work["total_lines"])

    def test_genre_counts(self):
        counts = Counter(work["genre"] for work in self.works)
        self.assertEqual(counts['Socratic'], 4)
        self.assertEqual(counts['History'], 3)
        self.assertEqual(counts['Technical'], 3)

    def test_unique_ids_and_abbreviations(self):
        work_ids = [work["play_id"] for work in self.works]
        abbrs = [work["abbr"] for work in self.works]
        self.assertEqual(len(work_ids), len(set(work_ids)))
        self.assertEqual(len(abbrs), len(set(abbrs)))

    def test_locations_follow_catalog_order(self):
        self.assertEqual(self.works[0]["location"], "01")


class TestParagraphs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paragraphs = json.loads((DATA_DIR / "chunks.json").read_text())
        cls.works = {work["play_id"] for work in json.loads((DATA_DIR / "plays.json").read_text())}

    def test_paragraphs_are_present(self):
        self.assertEqual(len(self.paragraphs), 6273)

    def test_first_paragraph_shape(self):
        first = self.paragraphs[0]
        self.assertEqual(first["canonical_id"], "Xen.Hell.1.1.1")
        self.assertEqual(first["location"], "01.001.0001.0001")
        self.assertEqual(first["act"], 1)
        self.assertEqual(first["chapter"], 1)
        self.assertEqual(first["section"], 1)

    def test_paragraph_has_required_fields(self):
        required = {"scene_id", "canonical_id", "location", "play_id", "act", "scene", "total_words", "num_lines", "hapax_count"}
        for paragraph in self.paragraphs[:25]:
            self.assertTrue(required.issubset(paragraph.keys()))
            self.assertEqual(paragraph["num_lines"], 1)

    def test_all_paragraphs_reference_valid_works(self):
        for paragraph in self.paragraphs:
            self.assertIn(paragraph["play_id"], self.works)

    def test_unique_scene_ids(self):
        paragraph_ids = [paragraph["scene_id"] for paragraph in self.paragraphs]
        self.assertEqual(len(paragraph_ids), len(set(paragraph_ids)))


class TestTokens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = json.loads((DATA_DIR / "tokens.json").read_text())

    def test_token_index_size(self):
        self.assertGreater(len(self.tokens), 35000)

    def test_xenophon_vocabulary_present(self):
        for word in ('καὶ', 'κῦρος', 'ἀθηναῖοι'):
            self.assertIn(word, self.tokens)
        self.assertGreater(len(self.tokens["κῦρος"]), 300)

    def test_posting_format(self):
        sample_key = next(iter(self.tokens))
        postings = self.tokens[sample_key]
        self.assertIsInstance(postings, list)
        self.assertGreater(len(postings), 0)
        for posting in postings[:5]:
            self.assertIsInstance(posting, list)
            self.assertEqual(len(posting), 2)
            self.assertIsInstance(posting[0], int)
            self.assertIsInstance(posting[1], int)


class TestParagraphRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((LINES_DIR / "all_lines.json").read_text())
        cls.paragraphs = json.loads((DATA_DIR / "chunks.json").read_text())

    def test_all_lines_matches_paragraph_count(self):
        self.assertEqual(len(self.rows), len(self.paragraphs))

    def test_rows_align_with_chunks_by_canonical_id(self):
        for row, chunk in zip(self.rows[:100], self.paragraphs[:100]):
            self.assertEqual(row["canonical_id"], chunk["canonical_id"])
        self.assertTrue(self.rows[0]["text"].strip())
        self.assertTrue(self.rows[-1]["text"].strip())


class TestPublishedMetadata(unittest.TestCase):
    def test_hapax_counts_and_instance_json(self):
        chunks = json.loads((DATA_DIR / "chunks.json").read_text())
        self.assertIn("hapax_count", chunks[0])
        self.assertGreater(sum(c["hapax_count"] for c in chunks), 15000)
        instance = json.loads((DATA_DIR.parent / "instance.json").read_text())
        self.assertEqual(instance["id"], "xenophon")
        self.assertEqual(instance["language"], "Greek")
        self.assertEqual(instance["created"], "2026-05-17")
        self.assertEqual(instance["stats"]["texts"], 14)
        self.assertEqual(instance["stats"]["segments"], 6273)
        self.assertEqual(instance["stats"]["words"], 312209)
        self.assertEqual(instance["stats"]["segment_label"], "segments")
        self.assertEqual(instance["stats"]["commentaries"], 0)
        self.assertEqual(instance["stats"]["comments"], 0)

    def test_characters_hold_per_book_aggregates_not_names(self):
        chars = json.loads((DATA_DIR / "characters.json").read_text())
        self.assertEqual(len(chars), 36)
        self.assertTrue(all(ch.get("total_words_spoken", 0) >= 0 for ch in chars))


if __name__ == "__main__":
    unittest.main()
