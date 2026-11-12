"""English reading aids from Wiktionary: a dictionary form and gloss per word.

Copy this file into an instance as `scripts/glossary.py` and set LANGUAGE and
EXTRACT_SHA256. It reads `source_text/lexicon/wiktionary-extract.json`, the
compact extract that `kaikki_extract.py` (in the contabulate-instances skill)
cuts from kaikki.org's Wiktionary dump, and builds the instance's
`docs/data/glossary.json`.

Unlike an analysis of the text itself, a dictionary cannot tell which word a
spelling is in a given place: Latin "est" is "is" far more often than "eats".
Each written form is therefore assigned to one dictionary word, the candidate
that accounts for most of this text (estimated over all its spellings, with a
form that is itself a headword preferred and a mere variant spelling
distrusted). Every occurrence in a spelling shared with another word is
counted as ambiguous (`amb`), which the page reports.
"""
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

LANGUAGE = "grc"
EXTRACT_FILE = "wiktionary-extract.json"
EXTRACT_SHA256 = "e416756070cb0c062e6fe45b703d1df9ff54c4c1bd94957bbb5258fe2a01681d"
ENCLITICS = {"la": ("que", "ne", "ve")}
POS_LABELS = {
    "noun": "noun", "verb": "verb", "adj": "adjective", "adv": "adverb", "prep": "preposition",
    "conj": "conjunction", "pron": "pronoun", "name": "name", "num": "numeral", "det": "determiner",
    "particle": "particle", "intj": "interjection", "article": "article", "postp": "postposition",
    "phrase": "phrase", "prep_phrase": "phrase", "contraction": "contraction",
}
# Words too common in glosses to say what a lemma means. They are indexed
# only for lemmas whose glosses contain nothing else.
STOP_WORDS = frozenset("""
a an the and or of to in on for with by from at as is are was were be been it its he she they them
their his her you your we our us i my me him who whom which that this those these then so but not
no will would shall should may might can could do does did have has had o if when what there than
am one esp etc something someone
""".split())


def normalize(word, language=LANGUAGE):
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


def candidates(token, language=LANGUAGE):
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


def load_extract(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != EXTRACT_SHA256:
        raise ValueError(f"Source checksum mismatch: {path}")
    return json.loads(data)


def gloss_words(gloss):
    plain = re.sub(r"\([^)]*\)", " ", gloss)
    words = [w for w in re.findall(r"[a-z]+(?:'[a-z]+)?", plain.lower()) if w not in STOP_WORDS]
    return words or re.findall(r"[a-z]+(?:'[a-z]+)?", gloss.lower())


FIRST_SENSE = 30  # a word in the leading senses outranks most later-sense matches
LEADING_SENSES = 2  # Greek βασιλεύς: "chief, master" first, "emperor, king" second


def word_index(glosses, count, limit=16):
    """English words weighted by the lemma's frequency. Wiktionary lists many
    senses; a frequent word's fifth sense must not outrank a rarer word's
    first, so words of the leading senses are weighted thirtyfold; a much
    more frequent word (λέγω for "say") can still come first."""
    weights = {}
    for position, gloss in enumerate(glosses):
        for word in gloss_words(gloss):
            weight = max(1, count) * (FIRST_SENSE if position < LEADING_SENSES else 1)
            weights[word] = max(weights.get(word, 0), weight)
    return [[w, c] for w, c in sorted(weights.items(), key=lambda wc: (-wc[1], wc[0]))[:limit]]


def short_definition(glosses, limit=70, cap=110):
    """The first sense, with the second where both are brief. Wiktionary
    sometimes explains at length before it translates; a long gloss is cut
    at a word boundary."""
    if not glosses:
        return ""
    text = glosses[0]
    if len(glosses) > 1 and len(text) + len(glosses[1]) + 2 <= limit:
        text += "; " + glosses[1]
    if len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0].rstrip(",;:") + " …"
    return text


# Parts of speech in the order a dictionary entry would list them when one
# headword has several: a spelling that is both a function word and a noun
# (Italian "di": the preposition, and the name of the letter D) is nearly
# always the function word.
POS_ORDER = [
    "prep", "conj", "article", "det", "pron", "particle", "adv", "postp", "contraction", "verb",
    "adj", "num", "noun", "intj", "phrase", "prep_phrase", "name",
]
KIND_ORDER = {"self": 0, "form": 1, "alt": 2}
KIND_TRUST = {"self": 3.0, "form": 1.0, "alt": 0.05}
# The search index is lower-cased, so a spelling shared by a common word and
# a proper name ("amor" and "Amor") is more often the common word.
NAME_TRUST = 0.5


def trust(lemma, kind):
    return KIND_TRUST[kind] * (NAME_TRUST if lemma[1] == "name" else 1.0)


# German keeps parts of speech apart (sein "to be", sein "his"); Greek and
# the other languages merge them under one headword.
MERGE_PARTS_OF_SPEECH = LANGUAGE != "de"
GREEK_ARTICLE_FORMS = frozenset(
    "ὁ ἡ τό τοῦ τῆς τῷ τῇ τόν τήν οἱ αἱ τά τῶν τοῖς ταῖς τούς τάς τώ τοῖν".split())


# Which part of speech names a merged headword: its central use first
# (κύριος is a noun, "lord", before an adjective; ὁ an article).
MERGE_ORDER = ["article", "noun", "verb", "adj", "pron", "det", "prep", "conj", "particle", "adv", "num", "name"]


def merge_rank(pos):
    return MERGE_ORDER.index(pos) if pos in MERGE_ORDER else len(MERGE_ORDER)


def pos_rank(pos):
    return POS_ORDER.index(pos) if pos in POS_ORDER else len(POS_ORDER)


def lookup(token, extract):
    """Candidate dictionary words for a written form: {(headword, pos): kind}.
    Parts of speech remain separate so grammatical homographs do not merge."""
    for key in candidates(token):
        found = extract["forms"].get(key.replace("’", "'"))
        if not found:
            continue
        if LANGUAGE == "grc":
            # Declension tables print the article beside each form, so the
            # article's forms show up as forms of hundreds of nouns and
            # adjectives; only the article itself owns them.
            if normalize(token) in GREEK_ARTICLE_FORMS:
                found = [f for f in found if f[0] == "ὁ"] or found
        if MERGE_PARTS_OF_SPEECH:
            # One headword, one candidate: Greek κύριος (noun "lord", adjective
            # "having power") and ὁ (article, pronoun) are one word each.
            merged = {}
            for lemma, pos, kind in found:
                best = merged.get(lemma)
                if best is None:
                    merged[lemma] = (pos, kind)
                else:
                    merged[lemma] = (min(best[0], pos, key=merge_rank), min(best[1], kind, key=KIND_ORDER.get))
            return {(lemma, pos): kind for lemma, (pos, kind) in merged.items()}
        # Preserve grammatical homographs: sein (be) is not sein (his).
        result = {(lemma, pos): kind for lemma, pos, kind in found}
        if LANGUAGE == "de" and "ß" in token:
            # A pre-1996 spelling counts as what its reformed spelling is:
            # "schloß" is "schloss" (the castle, or "closed"), "muß" is
            # "muss", "daß" is "dass". Wiktionary links the old spelling only
            # as a weak variant; the reformed one says which words it can be.
            reformed = extract["forms"].get(normalize(token).replace("ß", "ss"), [])
            strength = {(lemma, pos): kind for lemma, pos, kind in reformed}
            for candidate, kind in list(result.items()):
                better = strength.get(candidate)
                if kind == "alt" and better in ("self", "form"):
                    result[candidate] = better
        return result
    return {}


def estimate_weights(form_candidates, form_total, rounds=4):
    """How much of the text each dictionary word accounts for, sharing each
    ambiguous spelling among its candidates in proportion to their current
    estimates (a few rounds of expectation-maximization)."""
    weight = defaultdict(lambda: 1.0)
    for _ in range(rounds):
        new = defaultdict(float)
        for form, found in form_candidates.items():
            if not found:
                continue
            scores = {lemma: weight[lemma] * trust(lemma, kind) for lemma, kind in found.items()}
            total = sum(scores.values()) or 1.0
            for lemma, score in scores.items():
                new[lemma] += form_total[form] * score / total
        weight = defaultdict(float, new)
    return weight


def build_glossary(tokens, source_dir):
    """`tokens` is the instance's unigram index: {form: postings}."""
    extract = load_extract(Path(source_dir) / "lexicon" / EXTRACT_FILE)

    by_headword = defaultdict(list)
    for key in extract["lemmas"]:
        by_headword[key.split("\t")[0]].append(key)

    def senses_of(lemma):
        """A headword's glosses: those of the part of speech this spelling
        was matched under first, then the others."""
        word, pos = lemma
        senses = list(extract["lemmas"].get(f"{word}\t{pos}", []))
        if MERGE_PARTS_OF_SPEECH:
            # The headword's other parts of speech follow, by merge order.
            others = sorted((k.split("\t")[1] for k in by_headword.get(word, ()) if k.split("\t")[1] != pos),
                            key=merge_rank)
            for other in others:
                for gloss in extract["lemmas"].get(f"{word}\t{other}", [])[:2]:
                    if gloss not in senses:
                        senses.append(gloss)
        # The dictionary lists auxiliary grammar before the ordinary meaning.
        if word == "sein" and pos == "verb" and "to be" in senses:
            senses.remove("to be")
            senses.insert(0, "to be")
        return senses

    form_total = {form: sum(count for _, count in postings) for form, postings in tokens.items()}
    form_candidates = {form: lookup(form, extract) for form in tokens}

    weight = estimate_weights(form_candidates, form_total)
    stats = Counter()
    assigned = {}
    for form, found in form_candidates.items():
        stats["words"] += form_total[form]
        if not found:
            stats["words_without_lemma"] += form_total[form]
            stats["forms_without_lemma"] += 1
            form_candidates[form] = []
            continue
        if all(kind == "alt" for kind in found.values()):
            # Only variant spellings to go on (a contraction, an old spelling):
            # their frequency says nothing, so keep dictionary order.
            ranked = sorted(found, key=lambda lemma: pos_rank(lemma[1]))
        else:
            ranked = sorted(found, key=lambda lemma: -weight[lemma] * trust(lemma, found[lemma]))
        # Possessive declensions also appear in personal-pronoun tables.
        # Prefer the determiner, not e.g. er (he), for seine/seinen/etc.
        # Bare sein remains ambiguous (be/his); its spelling count is flagged.
        for base, stem in [("mein", "mein"), ("dein", "dein"), ("sein", "sein"),
                           ("ihr", "ihr"), ("unser", "uns(?:er|r)"), ("euer", "eu(?:er|r)")]:
            preferred = (base, "det")
            if re.fullmatch(stem + r"(?:e|en|em|er|es)", form) and preferred in ranked:
                ranked.remove(preferred)
                ranked.insert(0, preferred)
                break
        form_candidates[form] = ranked
        assigned[form] = ranked[0]
        if len(ranked) > 1:
            stats["words_in_shared_spellings"] += form_total[form]

    # One entry per headword and part of speech.
    lemma_forms = defaultdict(Counter)
    lemma_shared = Counter()
    for form, key in assigned.items():
        word, pos = key
        lemma_forms[key][form] += form_total[form]
        if len(form_candidates[form]) > 1:
            lemma_shared[key] += form_total[form]
    ordered = sorted(lemma_forms, key=lambda k: (-sum(lemma_forms[k].values()), k))
    index = {word: i for i, word in enumerate(ordered)}
    lemmas = []
    for key in ordered:
        word, pos = key
        count = sum(lemma_forms[key].values())
        senses = senses_of((word, pos))
        entry = {
            "lemma": word,
            "pos": POS_LABELS.get(pos, pos),
            "n": count,
            "def": short_definition(senses),
            "en": senses[2:4] if len(senses) > 2 else [],
            "w": word_index(senses, count),
            "forms": [[f, c] for f, c in sorted(lemma_forms[key].items(), key=lambda fc: (-fc[1], fc[0]))],
        }
        if lemma_shared[key]:
            entry["amb"] = lemma_shared[key]
        lemmas.append(entry)
    forms = {}
    for form in sorted(tokens):
        found = form_candidates[form]
        shown = []
        for lemma in found[:2]:
            text = short_definition(senses_of(lemma))
            if text and text not in shown:
                shown.append(text)
        forms[form] = [form_total[form], shown, [index[l] for l in found[:3] if l in index]]
    stats["lemmas"] = len(lemmas)
    stats["forms"] = len(forms)
    return {"forms": forms, "lemmas": lemmas}, stats, extract["source"]
