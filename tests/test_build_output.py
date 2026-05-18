from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
LINES_PATH = ROOT / "docs" / "lines" / "all_lines.json"


EXPECTED_TITLES = [
    "Hellenica",
    "Memorabilia",
    "Oeconomicus",
    "Symposium",
    "Apology",
    "Anabasis",
    "Cyropaedia",
    "Hiero",
    "Agesilaus",
    "Constitution of the Lacedaemonians",
    "Ways and Means",
    "On the Cavalry Commander",
    "On the Art of Horsemanship",
    "On Hunting",
]


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_expected_json_files_exist_and_are_non_empty():
    expected = [
        DATA_DIR / "plays.json",
        DATA_DIR / "characters.json",
        DATA_DIR / "chunks.json",
        DATA_DIR / "tokens.json",
        DATA_DIR / "tokens2.json",
        DATA_DIR / "tokens3.json",
        DATA_DIR / "tokens_char.json",
        DATA_DIR / "tokens_char2.json",
        DATA_DIR / "tokens_char3.json",
        DATA_DIR / "character_name_filter_config.json",
        LINES_PATH,
    ]
    for path in expected:
        assert path.exists(), f"Missing build artifact: {path}"
        assert path.stat().st_size > 0, f"Empty build artifact: {path}"


def test_works_and_book_units_have_expected_shape():
    plays = load_json(DATA_DIR / "plays.json")
    characters = load_json(DATA_DIR / "characters.json")

    assert [play["title"] for play in plays] == EXPECTED_TITLES
    assert len(plays) == 14
    assert plays[0]["num_acts"] == 7
    assert plays[5]["title"] == "Anabasis"
    assert plays[5]["num_acts"] == 7
    assert len(characters) == 36
    assert characters[0]["play_title"] == "Hellenica"
    assert characters[0]["name"] == "Βιβλίον α"
    assert characters[-1]["play_title"] == "On Hunting"
    assert characters[-1]["name"] == "On Hunting"


def test_chunks_lines_and_token_indexes_are_consistent():
    chunks = load_json(DATA_DIR / "chunks.json")
    all_lines = load_json(LINES_PATH)
    tokens = load_json(DATA_DIR / "tokens.json")
    tokens2 = load_json(DATA_DIR / "tokens2.json")
    tokens3 = load_json(DATA_DIR / "tokens3.json")

    assert len(chunks) == len(all_lines)
    assert len(chunks) > 6000

    chunk_ids = {chunk["scene_id"] for chunk in chunks}
    line_ids = {line["line_num"] for line in all_lines}
    assert chunk_ids == line_ids

    first_chunk = chunks[0]
    first_line = all_lines[0]
    assert first_chunk["canonical_id"] == "Xen.Hell.1.1.1"
    assert first_line["text"].startswith("μετὰ δὲ ταῦτα")
    assert first_chunk["act_label"] == "Βιβλίον α"

    for index in (tokens, tokens2, tokens3):
        sample_postings = next(iter(index.values()))
        assert sample_postings
        assert sample_postings[0][0] in chunk_ids
        assert sample_postings[0][1] > 0


def test_expected_xenophontic_terms_exist():
    tokens = load_json(DATA_DIR / "tokens.json")
    tokens2 = load_json(DATA_DIR / "tokens2.json")

    assert "σωκράτης" in tokens
    assert "κύρου" in tokens
    assert "στρατιώτας" in tokens
    assert "σωκράτης ἔφη" in tokens2
