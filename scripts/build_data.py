#!/usr/bin/env python3
"""Build static data files for the Xenophon contabulate app."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
LINES_DIR = ROOT / "docs" / "lines"
TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}
TOKEN_RE = re.compile(r"[^\W\d_]+(?:[᾽'][^\W\d_]+)?", re.UNICODE)

GREEK_BOOK_LETTERS = ["α", "β", "γ", "δ", "ε", "ζ", "η", "θ"]

WORK_SPECS = [
    {"id": 1, "urn": "tlg001", "title": "Hellenica", "abbr": "Hell.", "genre": "History", "sort_prefix": "01"},
    {"id": 2, "urn": "tlg002", "title": "Memorabilia", "abbr": "Mem.", "genre": "Socratic", "sort_prefix": "02"},
    {"id": 3, "urn": "tlg003", "title": "Oeconomicus", "display_title": "Economics", "abbr": "Oec.", "genre": "Socratic", "sort_prefix": "03"},
    {"id": 4, "urn": "tlg004", "title": "Symposium", "abbr": "Symp.", "genre": "Socratic", "sort_prefix": "04"},
    {"id": 5, "urn": "tlg005", "title": "Apology", "abbr": "Apol.", "genre": "Socratic", "sort_prefix": "05"},
    {"id": 6, "urn": "tlg006", "title": "Anabasis", "abbr": "An.", "genre": "History", "sort_prefix": "06"},
    {"id": 7, "urn": "tlg007", "title": "Cyropaedia", "abbr": "Cyr.", "genre": "History", "sort_prefix": "07"},
    {"id": 8, "urn": "tlg008", "title": "Hiero", "abbr": "Hier.", "genre": "Dialogue", "sort_prefix": "08"},
    {"id": 9, "urn": "tlg009", "title": "Agesilaus", "abbr": "Ages.", "genre": "Biography", "sort_prefix": "09"},
    {"id": 10, "urn": "tlg010", "title": "Constitution of the Lacedaemonians", "abbr": "Lac.", "genre": "Constitution", "sort_prefix": "10"},
    {"id": 11, "urn": "tlg011", "title": "Ways and Means", "abbr": "Vect.", "genre": "Political", "sort_prefix": "11"},
    {"id": 12, "urn": "tlg012", "title": "On the Cavalry Commander", "abbr": "Hipparch.", "genre": "Technical", "sort_prefix": "12"},
    {"id": 13, "urn": "tlg013", "title": "On the Art of Horsemanship", "abbr": "Eq.", "genre": "Technical", "sort_prefix": "13"},
    {"id": 14, "urn": "tlg014", "title": "On Hunting", "abbr": "Cyn.", "genre": "Technical", "sort_prefix": "14"},
]


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text or "")]


def ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"), ensure_ascii=False)


def dedup_postings(index: dict[str, list[list[int]]]) -> dict[str, list[list[int]]]:
    result: dict[str, list[list[int]]] = {}
    for term, postings in index.items():
        merged: dict[int, int] = {}
        for chunk_id, count in postings:
            merged[chunk_id] = merged.get(chunk_id, 0) + count
        result[term] = [[chunk_id, count] for chunk_id, count in sorted(merged.items())]
    return result


def build_character_indexes(characters: list[dict]) -> tuple[dict, dict, dict]:
    tokens1 = defaultdict(list)
    tokens2 = defaultdict(list)
    tokens3 = defaultdict(list)

    for character in characters:
        character_id = character["character_id"]
        name_tokens = tokenize(f"{character['play_title']} {character['name']}")
        counts1 = Counter(name_tokens)
        counts2 = Counter(ngrams(name_tokens, 2))
        counts3 = Counter(ngrams(name_tokens, 3))

        for term, count in counts1.items():
            tokens1[term].append([character_id, count])
        for term, count in counts2.items():
            tokens2[term].append([character_id, count])
        for term, count in counts3.items():
            tokens3[term].append([character_id, count])

    return dedup_postings(tokens1), dedup_postings(tokens2), dedup_postings(tokens3)


def text_content(elem: ET.Element) -> str:
    return " ".join("".join(elem.itertext()).split())


def source_path(spec: dict) -> Path:
    return ROOT / "source_text" / f"tlg0032.{spec['urn']}.perseus-grc2.xml"


def section_refs(body: ET.Element):
    """Yield citation context and section element in document order."""
    state = {"book": None, "chapter": None}

    def walk(elem: ET.Element, book_n: int | None, chapter_n: int | None):
        if elem.tag == f"{{{TEI_NS}}}div":
            subtype = (elem.attrib.get("subtype") or "").lower()
            n = (elem.attrib.get("n") or "").strip()
            if subtype == "book" and n.isdigit():
                book_n = int(n)
                chapter_n = None
            elif subtype == "chapter" and n.isdigit():
                chapter_n = int(n)
            elif subtype == "section" and n.isdigit():
                yield book_n, chapter_n, int(n), elem
                return
        for child in list(elem):
            yield from walk(child, book_n, chapter_n)

    yield from walk(body, state["book"], state["chapter"])


def count_top_books(body: ET.Element) -> int:
    return sum(
        1 for div in body.findall(".//tei:div", NS)
        if (div.attrib.get("subtype") or "").lower() == "book" and (div.attrib.get("n") or "").isdigit()
    )


def book_label(book_n: int | None, has_books: bool) -> str:
    if not has_books:
        return "Whole work"
    if book_n is None:
        return "Unbooked"
    letter = GREEK_BOOK_LETTERS[book_n - 1] if 1 <= book_n <= len(GREEK_BOOK_LETTERS) else str(book_n)
    return f"Βιβλίον {letter}"


def citation(spec: dict, book_n: int | None, chapter_n: int | None, section_n: int, has_books: bool) -> str:
    parts = [spec["abbr"].rstrip(".")]
    if has_books and book_n is not None:
        parts.append(str(book_n))
    if chapter_n is not None:
        parts.append(str(chapter_n))
    parts.append(str(section_n))
    return ".".join(parts)


def heading(spec: dict, book_n: int | None, chapter_n: int | None, section_n: int, has_books: bool) -> str:
    return f"Xenophon, {spec['title']} {citation(spec, book_n, chapter_n, section_n, has_books).split('.', 1)[1]}"


def build() -> None:
    plays = []
    characters = []
    chunks = []
    all_lines = []
    tokens1 = defaultdict(list)
    tokens2 = defaultdict(list)
    tokens3 = defaultdict(list)

    chunk_id = 0
    character_id = 0

    for spec in WORK_SPECS:
        tree = ET.parse(source_path(spec))
        root = tree.getroot()
        body = root.find(".//tei:body", NS)
        if body is None:
            raise ValueError(f"No <body> found in {source_path(spec)}")

        has_books = count_top_books(body) > 0
        work_total_words = 0
        work_total_sections = 0
        work_book_totals = Counter()
        work_book_sections = Counter()
        seen_book_keys = []

        for book_n, chapter_n, section_n, section_elem in section_refs(body):
            text = text_content(section_elem)
            if not text:
                continue

            chunk_id += 1
            toks = tokenize(text)
            total_words = len(toks)
            book_key = book_n if has_books and book_n is not None else 1
            chapter_key = chapter_n if chapter_n is not None else 0
            canonical_id = f"Xen.{citation(spec, book_n, chapter_n, section_n, has_books)}"
            location = f"{spec['sort_prefix']}.{book_key:03d}.{chapter_key:04d}.{section_n:04d}"
            label = book_label(book_n, has_books)

            if book_key not in seen_book_keys:
                seen_book_keys.append(book_key)

            chunks.append({
                "scene_id": chunk_id,
                "canonical_id": canonical_id,
                "location": location,
                "play_id": spec["id"],
                "play_title": spec["title"],
                "play_abbr": spec["abbr"],
                "genre": spec["genre"],
                "act": book_key,
                "act_label": label,
                "chapter": chapter_n,
                "chapter_label": f"Chapter {chapter_n}" if chapter_n is not None else "Sections",
                "section": section_n,
                "scene": (chapter_key * 1000) + section_n,
                "heading": heading(spec, book_n, chapter_n, section_n, has_books),
                "total_words": total_words,
                "unique_words": len(set(toks)),
                "num_speeches": 0,
                "num_lines": 1,
                "characters_present_count": 1,
            })
            all_lines.append({
                "play_id": spec["id"],
                "canonical_id": canonical_id,
                "location": location,
                "act": book_key,
                "act_label": label,
                "chapter": chapter_n,
                "chapter_label": f"Chapter {chapter_n}" if chapter_n is not None else "Sections",
                "section": section_n,
                "scene": (chapter_key * 1000) + section_n,
                "line_num": chunk_id,
                "text": text,
            })

            counts1 = Counter(toks)
            counts2 = Counter(ngrams(toks, 2))
            counts3 = Counter(ngrams(toks, 3))
            for term, count in counts1.items():
                tokens1[term].append([chunk_id, count])
            for term, count in counts2.items():
                tokens2[term].append([chunk_id, count])
            for term, count in counts3.items():
                tokens3[term].append([chunk_id, count])

            work_book_totals[book_key] += total_words
            work_book_sections[book_key] += 1
            work_total_words += total_words
            work_total_sections += 1

        plays.append({
            "play_id": spec["id"],
            "location": spec["sort_prefix"],
            "title": spec["title"],
            "display_title": spec.get("display_title", spec["title"]),
            "abbr": spec["abbr"],
            "genre": spec["genre"],
            "first_performance_year": None,
            "num_acts": len(seen_book_keys),
            "num_scenes": work_total_sections,
            "num_speeches": 0,
            "total_words": work_total_words,
            "total_lines": work_total_sections,
        })

        for book_key in seen_book_keys:
            character_id += 1
            label = book_label(book_key if has_books else None, has_books)
            characters.append({
                "character_id": character_id,
                "play_id": spec["id"],
                "play_title": spec["title"],
                "name": label if has_books else spec["title"],
                "gender": "A",
                "num_speeches": 0,
                "total_words_spoken": work_book_totals[book_key],
                "act_label": label,
                "num_lines": work_book_sections[book_key],
            })

    tokens1 = dedup_postings(tokens1)
    tokens2 = dedup_postings(tokens2)
    tokens3 = dedup_postings(tokens3)
    tokens_char, tokens_char2, tokens_char3 = build_character_indexes(characters)

    write_json(DATA_DIR / "plays.json", plays)
    write_json(DATA_DIR / "characters.json", characters)
    write_json(DATA_DIR / "chunks.json", chunks)
    write_json(DATA_DIR / "tokens.json", tokens1)
    write_json(DATA_DIR / "tokens2.json", tokens2)
    write_json(DATA_DIR / "tokens3.json", tokens3)
    write_json(DATA_DIR / "tokens_char.json", tokens_char)
    write_json(DATA_DIR / "tokens_char2.json", tokens_char2)
    write_json(DATA_DIR / "tokens_char3.json", tokens_char3)
    write_json(DATA_DIR / "character_name_filter_config.json", {})
    write_json(LINES_DIR / "all_lines.json", all_lines)

    print(
        f"Built {len(plays)} works, {len(characters)} work/book units, {len(chunks)} sections, "
        f"{len(tokens1)} unigrams, {len(tokens2)} bigrams, {len(tokens3)} trigrams."
    )


if __name__ == "__main__":
    build()
