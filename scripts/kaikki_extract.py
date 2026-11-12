#!/usr/bin/env python3
"""Reduce a kaikki.org Wiktionary dictionary to what one instance needs.

kaikki.org publishes English Wiktionary as one JSON line per entry, per
language (hundreds of megabytes). An instance needs only two things from it:
which dictionary words each of its written forms can belong to, and a short
English gloss for those words. This script streams the big file once and
writes a compact extract that the instance commits and pins by SHA-256, so
its build never needs the download.

    kaikki_extract.py DICTIONARY.jsonl TOKENS.json OUT.json --language la

Extract format:
  {"source": {...}, "forms": {normalized form: [[lemma, pos, kind], ...]},
   where kind is "self" (the form is that dictionary word's own headword),
   "form" (an inflected form of it), or "alt" (reached through a variant
   spelling, the weakest evidence),
   "lemmas": {"lemma\\tpos": [gloss, ...]}}

Wiktionary text is CC BY-SA 3.0 / GFDL; credit Wiktionary and kaikki.org.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ENCLITICS = {"la": ("que", "ne", "ve")}
LEXICAL_POS = {
    "noun", "verb", "adj", "adv", "prep", "conj", "pron", "name", "num", "particle", "intj", "det",
    "article", "postp", "phrase", "prep_phrase", "contraction",
}


def normalize(word, language):
    """The spelling under which a form is looked up. Case never counts.
    Latin: no macrons, j read as i, ligatures written out. Italian: the
    diaeresis that marks scansion is dropped, written accents are kept.
    German: as written (umlauts and eszett are letters). Ancient Greek:
    accents and breathings kept, a grave read as an acute, vowel-length
    marks dropped."""
    text = unicodedata.normalize("NFD", word.lower())
    if language == "la":
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = text.replace("j", "i").replace("æ", "ae").replace("œ", "oe")
    elif language == "it":
        text = text.replace("\u0308", "")
    elif language == "grc":
        text = text.replace("\u0300", "\u0301").replace("\u0304", "").replace("\u0306", "")
        text = text.replace("\u1fbd", "'").replace("\u02bc", "'").replace("\u2019", "'")
    return unicodedata.normalize("NFC", text)


ACUTE_TO_GRAVE = str.maketrans("áíóú", "àìòù")


def candidates(token, language):
    """Lookup keys for a token, most literal first."""
    keys = [normalize(token, language)]
    for enclitic in ENCLITICS.get(language, ()):
        if keys[0].endswith(enclitic) and len(keys[0]) > len(enclitic) + 1:
            keys.append(keys[0][: -len(enclitic)])
    if language == "it":
        # Editions differ on acute and grave; elided words are entered with
        # their apostrophe (l', ch', d').
        swapped = keys[0].translate(ACUTE_TO_GRAVE)
        if swapped != keys[0]:
            keys.append(swapped)
        # An elided word (l', ch', quell') loses its apostrophe in the index.
        # A token with no vowel can only be elided; any other is first taken
        # as written and as elided only if the dictionary lacks it.
        elided = keys[0] + "'"
        if not any(c in "aeiouàèéìòù" for c in keys[0]):
            keys = [elided] + keys
        else:
            keys.append(elided)
    if language == "grc":
        # An enclitic can throw a second accent onto the word before it
        # (ἔλεός); the dictionary has it with one.
        nfd = unicodedata.normalize("NFD", keys[0])
        accents = [i for i, c in enumerate(nfd) if c in "\u0301\u0342"]
        if len(accents) > 1:
            keys.append(unicodedata.normalize("NFC", nfd[:accents[-1]] + nfd[accents[-1] + 1:]))
        # An elided word (δ', ἀλλ', ἐπ') loses its apostrophe in the index.
        if keys[0][-1:] in "βγδθλμπτφχ" or (len(keys[0]) > 1 and keys[0][-1:] in "κ" and keys[0] not in ("ἐκ", "οὐκ")):
            keys = [keys[0] + "'"] + keys
        elif len(keys[0]) <= 3:
            keys.append(keys[0] + "'")  # δι' (διά), ἀπ' ... when the word itself is unknown
    return keys


# "Diener: agent noun of dienen; servant" is tagged like an inflected form but
# is a word in its own right.
DERIVED_PREFIXES = (
    "agent noun of", "female equivalent of", "male equivalent of", "diminutive of", "augmentative of",
    "verbal noun of", "abstract noun of", "nominalization of", "nominalisation of", "endearing form of",
    "pejorative of", "gerund of",
)


WEAK_TAGS = frozenset({
    "obsolete", "archaic", "dated", "rare", "dialectal", "nonstandard", "misspelling", "poetic",
    "uncommon", "proscribed", "historical",
})


def derived_gloss(sense):
    """The meaning of a derived word entered as "X of Y; meaning", or None."""
    texts = sense.get("glosses") or ()
    if not texts or not texts[-1].lower().startswith(DERIVED_PREFIXES):
        return None
    for target in sense.get("form_of") or sense.get("alt_of") or ():
        if target.get("extra"):
            return clean_gloss(target["extra"])
    text = texts[-1]
    return clean_gloss(text.split(";", 1)[1]) if ";" in text else clean_gloss(text)


def target_word(target):
    """The word a form-of note points to. Notes run on ("avere and", "in il",
    "grande m or f by sense"); the word is what comes first."""
    words = (target.get("word") or "").strip().split()
    return words[0].strip(",;:.") if words else ""


def clean_gloss(gloss):
    text = re.sub(r"\s+", " ", gloss).strip().rstrip(".:;")
    return text


def is_plain_form(form):
    return bool(form) and " " not in form and "-" not in form and not any(c.isdigit() for c in form)


def extract(dictionary_path, tokens, language, max_glosses=4, max_hops=3):
    wanted = set()
    for token in tokens:
        wanted.update(key.replace("’", "'") for key in candidates(token, language))
    direct = defaultdict(list)         # wanted form -> [(normalized word, pos)] it is, or is listed under
    listed_as_variant = set()          # (wanted form, node) pairs that come from an "alternative form" listing
    parents = defaultdict(list)        # (normalized word, pos) -> [(normalized target, pos, is variant)]
    glosses = defaultdict(list)        # (word, pos) -> [gloss], for entries with a meaning of their own
    spellings = defaultdict(list)      # (normalized word, pos) -> [word as Wiktionary heads it]
    entries = 0
    with open(dictionary_path, encoding="utf-8") as handle:
        for line in handle:
            entry = json.loads(line)
            entries += 1
            word = entry.get("word") or ""
            pos = entry.get("pos") or ""
            if not word or pos not in LEXICAL_POS or not is_plain_form(word):
                continue
            if word.isupper() and len(word) <= 3:
                continue  # abbreviations (IM, CH) that collide with short words once case is ignored
            key = normalize(word, language).replace("’", "'")
            node = (key, pos)
            if key in wanted and node not in direct[key]:
                direct[key].append(node)
            for sense in entry.get("senses", ()):
                # A variant spelling, or a form the dictionary marks as no
                # longer or not generally used, is weak evidence that a
                # spelling is that word here.
                variant = (not sense.get("form_of") and bool(sense.get("alt_of"))) or bool(
                    WEAK_TAGS.intersection(sense.get("tags") or ()))
                targets = sense.get("form_of") or sense.get("alt_of")
                own_meaning = derived_gloss(sense) if targets else None
                if own_meaning:
                    if word not in spellings[node]:
                        spellings[node].append(word)
                    if own_meaning not in glosses[(word, pos)] and len(glosses[(word, pos)]) < max_glosses:
                        glosses[(word, pos)].append(own_meaning)
                    continue
                if targets:
                    # "nobis" is a form of "nos", itself a form of "ego";
                    # "dicentes" of "dicens", a participle of "dico". Record
                    # the link and follow the chain afterwards.
                    for target in targets:
                        lemma = normalize(target_word(target), language).replace("’", "'")
                        if lemma and lemma != key and (lemma, pos, variant) not in parents[node]:
                            parents[node].append((lemma, pos, variant))
                    continue
                texts = sense.get("glosses") or ()
                if texts and "no-gloss" not in (sense.get("tags") or ()):
                    gloss = clean_gloss(texts[-1])
                    if word not in spellings[node]:
                        spellings[node].append(word)
                    if gloss and gloss not in glosses[(word, pos)] and len(glosses[(word, pos)]) < max_glosses:
                        glosses[(word, pos)].append(gloss)
            # The inflection table of any entry lists forms that belong to it.
            for form in entry.get("forms", ()):
                text = form.get("form") or ""
                tags = form.get("tags") or ()
                if not is_plain_form(text) or "table-tags" in tags or "inflection-template" in tags or "auxiliary" in tags:
                    continue
                form_key = normalize(text, language)
                if form_key in wanted and form_key != key:
                    if node not in direct[form_key]:
                        direct[form_key].append(node)
                        if "alternative" in tags:
                            listed_as_variant.add((form_key, node))
                    elif "alternative" not in tags:
                        listed_as_variant.discard((form_key, node))

    nodes_by_key = defaultdict(list)
    for known in set(spellings) | set(parents):
        nodes_by_key[known[0]].append(known)

    def dictionary_words(node, hops=0, seen=(), variant=False):
        """Entries with a meaning of their own that a node leads to, each
        with whether a variant spelling lies on the way. A node that only
        points elsewhere (a form, a participle, a variant) is followed."""
        if node in seen or hops > max_hops:
            return []
        found = [((word, node[1]), variant) for word in spellings.get(node, ())]
        for target, pos, is_variant in parents.get(node, ()):
            # A contraction points to a preposition, a participle to a verb:
            # where the target is not entered under the same part of speech,
            # take it under whichever it has.
            same = (target, pos)
            targets = [same] if (same in spellings or same in parents) else nodes_by_key.get(target, [])
            for next_node in targets:
                for answer in dictionary_words(next_node, hops + 1, seen + (node,), variant or is_variant):
                    if answer[0] not in [f[0] for f in found]:
                        found.append(answer)
        return found

    out_forms = {}
    used = set()
    for key, nodes in direct.items():
        resolved = {}
        for node in nodes:
            for (word, pos), variant in dictionary_words(node, variant=(key, node) in listed_as_variant):
                if normalize(word, language) == key and node == (key, pos) and not variant:
                    kind = "self"
                else:
                    kind = "alt" if variant else "form"
                rank = {"self": 0, "form": 1, "alt": 2}
                if (word, pos) not in resolved or rank[kind] < rank[resolved[(word, pos)]]:
                    resolved[(word, pos)] = kind
        if resolved:
            out_forms[key] = [[word, pos, kind] for (word, pos), kind in resolved.items()]
            used.update(resolved)
    out_lemmas = {f"{word}\t{pos}": glosses[(word, pos)] for word, pos in sorted(used)}
    return out_forms, out_lemmas, entries


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dictionary", type=Path)
    parser.add_argument("tokens", type=Path, help="the instance's docs/data/tokens.json")
    parser.add_argument("out", type=Path)
    parser.add_argument("--language", required=True, choices=["la", "de", "it", "grc"])
    parser.add_argument("--url", default="")
    parser.add_argument("--published", default="", help="Last-Modified date of the download")
    args = parser.parse_args()

    tokens = list(json.loads(args.tokens.read_text(encoding="utf-8")))
    forms, lemmas, entries = extract(args.dictionary, tokens, args.language)
    covered = sum(1 for t in tokens if any(k.replace("’", "'") in forms for k in candidates(t, args.language)))
    payload = {
        "source": {
            "name": "English Wiktionary via kaikki.org (Wiktextract)",
            "url": args.url,
            "published": args.published,
            "extracted": datetime.date.today().isoformat(),
            "license": "CC BY-SA 3.0 / GFDL (Wiktionary contributors)",
            "language": args.language,
        },
        "forms": dict(sorted(forms.items())),
        "lemmas": lemmas,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"{entries} entries read; {covered} of {len(tokens)} written forms found "
          f"({covered / max(1, len(tokens)):.1%}); {len(lemmas)} dictionary words.")
    print(f"sha256 {digest}  {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
