#!/usr/bin/env python3
"""Post-build metric augmentation: adds the text-metric fields the shared
contabulate UI derives its optional columns from (sentence/char/rarity sums,
hapax counts, per-work MATTR) plus docs/instance.json for the hub.

Run after scripts/build_data.py: python3 scripts/augment_metrics.py
"""
import datetime
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import tokenize  # the build's own tokenizer, for fidelity

SENT_RE = re.compile(r"[.;··!?]+")


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def dump(name, value):
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    chunks = load("chunks.json")
    plays = load("plays.json")
    tokens = load("tokens.json")
    lines = json.loads((ROOT / "docs" / "lines" / "all_lines.json").read_text(encoding="utf-8"))

    corpus_freq = {tok: sum(c for _, c in postings) for tok, postings in tokens.items()}
    corpus_total = sum(corpus_freq.values()) or 1
    tok_rarity = {tok: -math.log10(f / corpus_total) for tok, f in corpus_freq.items()}
    chars = {}
    rarity = {}
    hapax = {}
    for tok, postings in tokens.items():
        L = len(tok)
        r = tok_rarity[tok]
        for sid, c in postings:
            chars[sid] = chars.get(sid, 0) + L * c
            rarity[sid] = rarity.get(sid, 0.0) + r * c
        if corpus_freq[tok] == 1:
            sid = postings[0][0]
            hapax[sid] = hapax.get(sid, 0) + 1

    text_by_sid = {}
    for ln, ch in zip(lines, chunks):
        text_by_sid[ch["scene_id"]] = ln.get("text", "")
    for ch in chunks:
        sid = ch["scene_id"]
        ch["sentence_count"] = len(SENT_RE.findall(text_by_sid.get(sid, "")))
        ch["char_count"] = chars.get(sid, 0)
        ch["rarity_sum"] = round(rarity.get(sid, 0.0), 3)
        ch["hapax_count"] = hapax.get(sid, 0)

    def mattr(toks, window=50):
        if not toks:
            return 0.0
        if len(toks) < window:
            return len(set(toks)) / len(toks)
        ratios = [len(set(toks[i:i + window])) / window for i in range(len(toks) - window + 1)]
        return sum(ratios) / len(ratios)

    stream_by_play = {}
    for ln in lines:
        stream_by_play.setdefault(ln["play_id"], []).extend(tokenize(ln.get("text", "")))
    for p in plays:
        p["mattr_50"] = round(mattr(stream_by_play.get(p["play_id"], [])), 3)

    dump("chunks.json", chunks)
    dump("plays.json", plays)

    meta_path = ROOT / "instance-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    payload = {
        "schema": 1,
        **meta,
        "updated": datetime.date.today().isoformat(),
        "stats": {
            "texts": len(plays),
            "text_label": meta.get("text_label", "works"),
            "segments": len(chunks),
            "segment_label": meta.get("segment_label", "segments"),
            "words": sum(p.get("total_words", 0) for p in plays),
            "distinct_words": len(tokens),
        },
    }
    payload.pop("text_label", None)
    payload.pop("segment_label", None)
    (ROOT / "docs" / "instance.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("chunks:", len(chunks), "| hapax total:", sum(hapax.values()), "| stats:", payload["stats"])


if __name__ == "__main__":
    main()
