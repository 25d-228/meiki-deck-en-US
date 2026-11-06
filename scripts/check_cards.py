"""Basic text-source checks; editorial review remains a separate requirement."""

import json
import re
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COUNTS = {"01": 800, "02": 1000, "03": 1200, "04": 1400,
          "05": 1600, "06": 1800, "07": 1200}
REQUIRED = {"schema_version", "id", "locale", "sentence", "cloze", "answer",
            "accepted_answers", "lemma", "meaning", "part_of_speech"}
OPTIONAL = {"register", "note"}
SUPPORT = {"pronunciation", "usage", "prosody", "social"}


def lengths(value):
    value = unicodedata.normalize("NFC", value)
    return (len(re.findall(r"[^\W_]+(?:['’][^\W_]+)*", value)),
            sum(not char.isspace() for char in value))


def check_card(card, stage):
    assert isinstance(card, dict) and set(card) == {"common", "language_specific"}
    common, support = card["common"], card["language_specific"]
    assert isinstance(common, dict) and REQUIRED <= set(common) <= REQUIRED | OPTIONAL
    assert type(common["schema_version"]) is int and common["schema_version"] == 2
    assert common["locale"] == "en-US"
    for key in set(common) - {"schema_version", "accepted_answers"}:
        value = common[key]
        assert isinstance(value, str) and value.strip(), key
        assert unicodedata.is_normalized("NFC", value), key
    assert re.fullmatch(rf"en-US-{stage}-\d{{4}}", common["id"]), "ID"
    variants = common["accepted_answers"]
    assert isinstance(variants, list), "accepted_answers"
    assert len(variants) == len(set(variants)), "duplicate accepted answer"
    for value in variants:
        assert isinstance(value, str) and value.strip(), "accepted answer"
        assert unicodedata.is_normalized("NFC", value), "accepted answer NFC"
        assert value != common["answer"], "redundant accepted answer"
    assert common["answer"] == common["cloze"], "answer/cloze"
    cloze, sentence = common["cloze"], common["sentence"]
    assert sum(sentence.startswith(cloze, i) for i in range(len(sentence))) == 1, "cloze occurrence"
    start = sentence.index(cloze)
    assert not unicodedata.combining(sentence[start]), "cloze start"
    end = start + len(cloze)
    assert end == len(sentence) or not unicodedata.combining(sentence[end]), "cloze end"
    caps = (12, 90) if stage == "01" else (16, 120) if stage == "02" else (20, 150)
    words, chars = lengths(sentence)
    assert words <= caps[0] and chars <= caps[1], "sentence cap"
    for value in [cloze, *variants]:
        words, chars = lengths(value)
        assert words <= 5 and chars <= 40, "cloze/variant cap"
    assert isinstance(support, dict) and set(support) <= SUPPORT, "support keys"
    for key, value in support.items():
        assert isinstance(value, str) and value.strip(), key
        assert unicodedata.is_normalized("NFC", value), key
    if "noun" in common["part_of_speech"].lower() and "pronoun" not in common["part_of_speech"].lower():
        assert "usage" in support, "noun usage support"


def check_stage(stage):
    cards = json.loads((ROOT / f"cards/en-US/{stage}.json").read_text())
    assert isinstance(cards, list) and len(cards) == COUNTS[stage], "stage count"
    expected = [f"en-US-{stage}-{i:04d}" for i in range(1, COUNTS[stage] + 1)]
    assert [card["common"]["id"] for card in cards] == expected, "ordered IDs"
    for card in cards:
        try:
            check_card(card, stage)
        except (AssertionError, KeyError, TypeError) as error:
            raise AssertionError(f'{card.get("common", {}).get("id", "unknown")}: {error}') from error
    coverage = (ROOT / f"coverage/en-US/{stage}.md").read_text()
    rows = []
    blocks = {}
    for line in coverage.splitlines():
        fields = [field.strip() for field in line.strip().strip("|").split("|")]
        if fields and re.fullmatch(r"en-US-\d{2}-\d{4}", fields[0]):
            assert len(fields) == 3 and all(fields), "coverage row"
            rows.append(fields)
        elif len(fields) == 5 and re.fullmatch(rf"{stage}-[A-Z]", fields[0]):
            first, last = re.findall(rf"en-US-{stage}-\d{{4}}", fields[4])
            blocks[fields[0]] = (int(fields[3]), first, last)
    assert [row[0] for row in rows] == expected, "one ordered coverage row per card"
    assert blocks, "coverage blocks"
    for block, (count, first, last) in blocks.items():
        actual = [row[0] for row in rows if row[1] == block]
        planned = [f"en-US-{stage}-{i:04d}" for i in range(int(first[-4:]), int(last[-4:]) + 1)]
        assert len(actual) == count and actual == planned, f"block {block}"
    assert all(row[1] in blocks for row in rows), "unallocated block"
    seen_ids, seen_sentences = set(), set()
    for path in sorted((ROOT / "cards/en-US").glob("*.json")):
        if path.stem > stage:
            continue
        for card in json.loads(path.read_text()):
            common = card["common"]
            sentence = unicodedata.normalize("NFC", " ".join(common["sentence"].split())).casefold()
            assert common["id"] not in seen_ids, "duplicate ID"
            assert sentence not in seen_sentences, f'duplicate sentence: {common["id"]}'
            seen_ids.add(common["id"])
            seen_sentences.add(sentence)
    print(f"PASS stage {stage}: {len(cards)} cards and coverage rows; fields, IDs, clozes, caps and duplicates.")


if __name__ == "__main__":
    assert len(sys.argv) == 2 and sys.argv[1] in COUNTS, "Usage: check_cards.py NN"
    check_stage(sys.argv[1])
