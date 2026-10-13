"""Small valid reference records for import/publication behavior."""

import json


def reference_word(identifier=1, sense_id=101, definition="a financial institution"):
    return {
        "id": identifier,
        "lemma": "bank",
        "display_form": "bank",
        "entry_type": "word",
        "alternatives": [["banking", "variant"]],
        "inflections": ["banks"],
        "senses": [
            {
                "id": sense_id,
                "definition": definition,
                "pos": "noun",
                "headword": "bank",
                "phrase_title": None,
                "ipa_uk": "bæŋk",
                "ipa_us": None,
                "entry_order": 0,
                "sense_order": 0,
            }
        ],
    }


def reference_file(path, records):
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))
    return path
