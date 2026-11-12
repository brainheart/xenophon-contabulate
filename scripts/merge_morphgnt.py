#!/usr/bin/env python3
"""Fill gaps in a Greek Wiktionary extract from the Greek New Testament's
word-by-word analysis.

Wiktionary's Ancient Greek inflection tables are uneven (no regular plural for
υἱός, few contracted participles, no entry for καθώς). The Greek New
Testament instance has a dictionary form for every one of its 137,741 words
(MorphGNT SBLGNT, CC BY-SA 3.0) and Dodson's public-domain gloss for each.
For written forms of another Greek instance that Wiktionary does not cover,
this adds the dictionary form the New Testament gives the same spelling.

    merge_morphgnt.py EXTRACT.json TOKENS.json GNT_GLOSSARY.json

The extract is rewritten in place; print its new SHA-256 for glossary.py.
Forms already found in Wiktionary are left alone.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kaikki_extract import candidates  # noqa: E402

POS_CODES = {
    "noun": "noun", "verb": "verb", "adjective": "adj", "adverb": "adv", "preposition": "prep",
    "conjunction": "conj", "pronoun": "pron", "article": "article", "particle": "particle",
    "interjection": "intj",
}


def main(extract_path, tokens_path, gnt_path):
    extract = json.loads(Path(extract_path).read_text(encoding="utf-8"))
    tokens = json.loads(Path(tokens_path).read_text(encoding="utf-8"))
    gnt = json.loads(Path(gnt_path).read_text(encoding="utf-8"))
    lemmas = gnt["lemmas"]
    added_forms = 0
    added_words = 0
    for token in tokens:
        keys = [k.replace("\u2019", "'") for k in candidates(token, "grc")]
        if any(k in extract["forms"] for k in keys):
            continue
        entry = gnt["forms"].get(token)
        if not entry or not entry[2]:
            continue
        found = []
        for i in entry[2]:
            lemma = lemmas[i]
            pos = POS_CODES.get(lemma["pos"], "particle")
            found.append([lemma["lemma"], pos, "form"])
            key = f"{lemma['lemma']}\t{pos}"
            if key not in extract["lemmas"] and lemma.get("def"):
                extract["lemmas"][key] = [lemma["def"]]
        extract["forms"][keys[-1] if keys[0].endswith("'") else keys[0]] = found
        added_forms += 1
        added_words += sum(c for _, c in tokens[token])
    extract["source"]["supplement"] = (
        "Forms missing from Wiktionary filled from the Greek New Testament instance: MorphGNT SBLGNT 6.12 "
        "lemmas (CC BY-SA 3.0) with Dodson's public-domain glosses")
    Path(extract_path).write_text(json.dumps(extract, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{added_forms} written forms ({added_words} words) filled from the New Testament analysis")
    print("sha256", hashlib.sha256(Path(extract_path).read_bytes()).hexdigest())


if __name__ == "__main__":
    main(*sys.argv[1:4])
