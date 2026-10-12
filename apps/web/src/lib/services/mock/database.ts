const database = {
  "account": {
    "id": "preview-alex",
    "display_name": "Alex",
    "handle": "alex",
    "bio": "Small expressions for everyday connections.",
    "joined_at": "2024-05-24T08:00:00Z",
    "plan": "pro",
    "library_node_id": "preview-library",
    "personal_node_id": "preview-personal",
    "published_node_id": "preview-published",
    "settings": {
      "locale": "en",
      "timezone": "Asia/Ho_Chi_Minh",
      "translation_language": "vi",
      "assistant": { "auto_approve": false },
      "learning": {
        "question_types": [
          "DEFINITION_TO_WORD",
          "CONTEXT_TO_WORD",
          "CLOZE_TO_WORD",
          "WORD_TO_DEFINITION",
          "WORD_TO_USAGE",
          "DIALOGUE_COMPLETION",
          "MEANING_IN_CONTEXT",
          "SENTENCE_REWRITE"
        ],
        "formats": [
          "SINGLE_CHOICE",
          "SINGLE_WORD",
          "SHORT_ANSWER"
        ],
        "questions_per_sense": 2,
        "max_sense_count": 10
      }
    },
    "effective_learning": {
      "question_types": [
        "DEFINITION_TO_WORD",
        "CONTEXT_TO_WORD",
        "CLOZE_TO_WORD",
        "WORD_TO_DEFINITION",
        "WORD_TO_USAGE",
        "DIALOGUE_COMPLETION",
        "MEANING_IN_CONTEXT",
        "SENTENCE_REWRITE"
      ],
      "formats": [
        "SINGLE_CHOICE",
        "SINGLE_WORD",
        "SHORT_ANSWER"
      ],
      "questions_per_sense": 2,
      "max_sense_count": 10
    },
    "learning_restriction": null,
    "learning_options": {
      "pairs": [
        {
          "question_type": "DEFINITION_TO_WORD",
          "format": "SINGLE_CHOICE",
          "level": 1
        },
        {
          "question_type": "DEFINITION_TO_WORD",
          "format": "SINGLE_WORD",
          "level": 3
        },
        {
          "question_type": "CONTEXT_TO_WORD",
          "format": "SINGLE_CHOICE",
          "level": 2
        },
        {
          "question_type": "CONTEXT_TO_WORD",
          "format": "SINGLE_WORD",
          "level": 3
        },
        {
          "question_type": "CLOZE_TO_WORD",
          "format": "SINGLE_CHOICE",
          "level": 2
        },
        {
          "question_type": "CLOZE_TO_WORD",
          "format": "SINGLE_WORD",
          "level": 3
        },
        {
          "question_type": "WORD_TO_DEFINITION",
          "format": "SINGLE_CHOICE",
          "level": 1
        },
        {
          "question_type": "WORD_TO_DEFINITION",
          "format": "SHORT_ANSWER",
          "level": 4
        },
        {
          "question_type": "WORD_TO_USAGE",
          "format": "SINGLE_CHOICE",
          "level": 2
        },
        {
          "question_type": "WORD_TO_USAGE",
          "format": "SHORT_ANSWER",
          "level": 4
        },
        {
          "question_type": "DIALOGUE_COMPLETION",
          "format": "SINGLE_CHOICE",
          "level": 2
        },
        {
          "question_type": "MEANING_IN_CONTEXT",
          "format": "SINGLE_CHOICE",
          "level": 2
        },
        {
          "question_type": "SENTENCE_REWRITE",
          "format": "SINGLE_CHOICE",
          "level": 2
        },
        {
          "question_type": "SENTENCE_REWRITE",
          "format": "SHORT_ANSWER",
          "level": 5
        }
      ],
      "limits": {
        "min_questions_per_sense": 1,
        "max_questions_per_sense": 4,
        "max_questions_per_prepare": 60
      },
      "advanced_grading": true
    }
  },
  "public_users": [
    {
      "id": "preview-sam",
      "display_name": "Sam",
      "handle": "sam",
      "bio": "Useful language for journeys and small discoveries.",
      "joined_at": "2024-08-12T08:00:00Z",
      "published_node_id": "preview-sam-published"
    }
  ],
  "summary": {
    "total": 48,
    "new": 12,
    "studied": 36,
    "due": 12,
    "not_due": 24,
    "reachable_decks": 9
  },
  "nodes": [
    {
      "id": "everyday",
      "parent_id": "preview-personal",
      "name": "Everyday conversation",
      "type": "DECK",
      "description": "Small expressions for everyday connections.",
      "counts": {
        "total": 36,
        "new": 9,
        "studied": 27,
        "due": 9,
        "not_due": 18,
        "reachable_decks": 1
      }
    },
    {
      "id": "business",
      "parent_id": "preview-personal",
      "name": "Business English",
      "type": "FOLDER",
      "description": "Work, communication and office vocabulary.",
      "counts": {
        "total": 36,
        "new": 9,
        "studied": 27,
        "due": 9,
        "not_due": 18,
        "reachable_decks": 6
      }
    },
    {
      "id": "travel",
      "parent_id": "preview-personal",
      "name": "Travel essentials",
      "type": "REFERENCE",
      "description": "A saved reference to a published deck.",
      "counts": {
        "total": 12,
        "new": 3,
        "studied": 9,
        "due": 3,
        "not_due": 6,
        "reachable_decks": 1
      }
    },
    {
      "id": "saved-business",
      "parent_id": "preview-personal",
      "name": "Business collection",
      "type": "REFERENCE",
      "description": "A saved reference to the Business English folder.",
      "counts": {
        "total": 36,
        "new": 9,
        "studied": 27,
        "due": 9,
        "not_due": 18,
        "reachable_decks": 6
      }
    },
    {
      "id": "published-everyday",
      "parent_id": "preview-published",
      "name": "A few useful expressions",
      "type": "DECK",
      "description": "Expressions worth sharing.",
      "counts": {
        "total": 12,
        "new": 3,
        "studied": 9,
        "due": 3,
        "not_due": 6,
        "reachable_decks": 1
      }
    }
  ],
  "library": {
    "created_at": "2026-08-12T08:00:00Z",
    "updated_at": "2026-10-05T09:30:00Z",
    "due_sense_ids": [
      1,
      5,
      9,
      13,
      17,
      21,
      25,
      29,
      33,
      37,
      41,
      45
    ],
    "new_sense_ids": [
      2,
      6,
      10,
      14,
      18,
      22,
      26,
      30,
      34,
      38,
      42,
      46
    ],
    "references": {
      "travel": "travel-source",
      "saved-business": "business",
      "saved-meetings": "meetings",
      "unavailable-reference": "removed-source"
    },
    "membership": {
      "everyday": [
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48
      ],
      "business-core": [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24
      ],
      "workplace": [
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36
      ],
      "meeting-expressions": [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12
      ],
      "email-expressions": [
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24
      ],
      "presentation-expressions": [
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36
      ],
      "travel-source": [
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48
      ],
      "published-everyday": [
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48
      ],
      "empty-deck": []
    },
    "nodes": [
      {
        "id": "meetings",
        "parent_id": "business",
        "name": "Meetings",
        "type": "FOLDER",
        "description": "Make room for every idea."
      },
      {
        "id": "emails",
        "parent_id": "business",
        "name": "Emails",
        "type": "FOLDER",
        "description": "Clear, considered correspondence."
      },
      {
        "id": "presentations",
        "parent_id": "business",
        "name": "Presentations",
        "type": "FOLDER",
        "description": "Ideas, explained simply."
      },
      {
        "id": "business-core",
        "parent_id": "business",
        "name": "Business Core",
        "type": "DECK",
        "description": "The language of decisions, ideas and working together."
      },
      {
        "id": "workplace",
        "parent_id": "business",
        "name": "Workplace Verbs",
        "type": "DECK",
        "description": "Useful verbs for getting things done."
      },
      {
        "id": "meeting-expressions",
        "parent_id": "meetings",
        "name": "Meeting expressions",
        "type": "DECK",
        "description": "Conversations around the table."
      },
      {
        "id": "email-expressions",
        "parent_id": "emails",
        "name": "Email essentials",
        "type": "DECK",
        "description": "Following up and keeping in touch."
      },
      {
        "id": "presentation-expressions",
        "parent_id": "presentations",
        "name": "Present with confidence",
        "type": "DECK",
        "description": "Opening, explaining and bringing ideas together."
      },
      {
        "id": "empty-deck",
        "parent_id": "emails",
        "name": "Draft expressions",
        "type": "DECK",
        "description": null
      },
      {
        "id": "saved-meetings",
        "parent_id": "emails",
        "name": "Meeting notes",
        "type": "REFERENCE",
        "description": "A reference to the Meetings folder."
      },
      {
        "id": "unavailable-reference",
        "parent_id": "emails",
        "name": "Saved correspondence",
        "type": "REFERENCE",
        "description": null
      },
      {
        "id": "travel-source",
        "parent_id": "preview-sam-published",
        "name": "Travel essentials",
        "type": "DECK",
        "description": "A published collection by Sam. This is the source of your saved reference."
      }
    ]
  },
  "activity": {
    "longest_streak": 12,
    "days": [
      {
        "days_ago": 0,
        "applied_events": 0,
        "practice_events": 0
      },
      {
        "days_ago": 1,
        "applied_events": 18,
        "practice_events": 2
      },
      {
        "days_ago": 2,
        "applied_events": 13,
        "practice_events": 3
      },
      {
        "days_ago": 3,
        "applied_events": 28,
        "practice_events": 4
      },
      {
        "days_ago": 4,
        "applied_events": 9,
        "practice_events": 0
      },
      {
        "days_ago": 5,
        "applied_events": 20,
        "practice_events": 5
      },
      {
        "days_ago": 6,
        "applied_events": 3,
        "practice_events": 1
      },
      {
        "days_ago": 8,
        "applied_events": 14,
        "practice_events": 0
      },
      {
        "days_ago": 10,
        "applied_events": 7,
        "practice_events": 2
      },
      {
        "days_ago": 11,
        "applied_events": 16,
        "practice_events": 0
      },
      {
        "days_ago": 14,
        "applied_events": 24,
        "practice_events": 6
      },
      {
        "days_ago": 16,
        "applied_events": 2,
        "practice_events": 1
      },
      {
        "days_ago": 18,
        "applied_events": 12,
        "practice_events": 0
      },
      {
        "days_ago": 22,
        "applied_events": 26,
        "practice_events": 4
      },
      {
        "days_ago": 23,
        "applied_events": 5,
        "practice_events": 2
      },
      {
        "days_ago": 27,
        "applied_events": 15,
        "practice_events": 0
      }
    ]
  },
  "schedule": [
    {
      "days_ahead": 0,
      "count": 2
    },
    {
      "days_ahead": 1,
      "count": 8
    },
    {
      "days_ahead": 2,
      "count": 16
    },
    {
      "days_ahead": 3,
      "count": 0
    },
    {
      "days_ahead": 4,
      "count": 12
    },
    {
      "days_ahead": 5,
      "count": 6
    },
    {
      "days_ahead": 6,
      "count": 4
    }
  ],
  "preparation": {
    "max_sense_count": 10,
    "questions_per_sense": 3
  },
  "dictionary": {
    "words": [
      {
        "id": 1001,
        "lemma": "run",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 49,
            "word_id": 1001,
            "pos": "VERB",
            "tier": "CORE",
            "definition": {
              "id": 491,
              "content": "to move quickly on foot",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4901,
                "content": "She [ran|p] to catch the bus.",
                "theme_id": null
              },
              {
                "id": 4902,
                "content": "He [ran|p] across the field.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "run",
                "inf": "BASE"
              },
              {
                "surface": "ran",
                "inf": "PAST"
              },
              {
                "surface": "run",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "runs",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "running",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A1",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 50,
            "word_id": 1001,
            "pos": "VERB",
            "tier": "CORE",
            "definition": {
              "id": 501,
              "content": "to operate or function",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5001,
                "content": "The engine [runs|3] smoothly.",
                "theme_id": null
              },
              {
                "id": 5002,
                "content": "Does this software [run] on your phone?",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "run",
                "inf": "BASE"
              },
              {
                "surface": "ran",
                "inf": "PAST"
              },
              {
                "surface": "run",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "runs",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "running",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A1",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 51,
            "word_id": 1001,
            "pos": "NOUN",
            "tier": "CORE",
            "definition": {
              "id": 511,
              "content": "an occasion when you run",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5101,
                "content": "We went for a short [run].",
                "theme_id": null
              },
              {
                "id": 5102,
                "content": "Her morning [run] takes twenty minutes.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "runs",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A1",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 53,
            "word_id": 1001,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 531,
              "content": "to manage or be in charge of an organization or activity",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5301,
                "content": "She [runs|3] a small café.",
                "theme_id": null
              },
              {
                "id": 5302,
                "content": "Who is running the training program?",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "run",
                "inf": "BASE"
              },
              {
                "surface": "ran",
                "inf": "PAST"
              },
              {
                "surface": "run",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "runs",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "running",
                "inf": "ING"
              }
            ],
            "patterns": [
              "run {sth}"
            ],
            "collocations": [
              "run a business",
              "run a course"
            ],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 54,
            "word_id": 1001,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 541,
              "content": "to travel along a particular route or at a particular time",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5401,
                "content": "The train [runs|3] every half hour.",
                "theme_id": null
              },
              {
                "id": 5402,
                "content": "Buses do not run after midnight.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "run",
                "inf": "BASE"
              },
              {
                "surface": "ran",
                "inf": "PAST"
              },
              {
                "surface": "run",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "runs",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "running",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 55,
            "word_id": 1001,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 551,
              "content": "to make a machine, program, or process operate",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5501,
                "content": "Can you [run] the test again?",
                "theme_id": null
              },
              {
                "id": 5502,
                "content": "The team ran several checks.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "run",
                "inf": "BASE"
              },
              {
                "surface": "ran",
                "inf": "PAST"
              },
              {
                "surface": "run",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "runs",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "running",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [
              "run a test",
              "run a program"
            ],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 56,
            "word_id": 1001,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 561,
              "content": "to flow in a particular direction",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5601,
                "content": "Water [runs|3] down the hill.",
                "theme_id": null
              },
              {
                "id": 5602,
                "content": "Tears ran down her cheeks.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "run",
                "inf": "BASE"
              },
              {
                "surface": "ran",
                "inf": "PAST"
              },
              {
                "surface": "run",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "runs",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "running",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 57,
            "word_id": 1001,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 571,
              "content": "to continue for a period of time",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5701,
                "content": "The exhibition [runs|3] until Sunday.",
                "theme_id": null
              },
              {
                "id": 5702,
                "content": "The meeting ran for two hours.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "run",
                "inf": "BASE"
              },
              {
                "surface": "ran",
                "inf": "PAST"
              },
              {
                "surface": "run",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "runs",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "running",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 58,
            "word_id": 1001,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 581,
              "content": "a series of similar events or a period of success or failure",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5801,
                "content": "The team had a [run] of five victories.",
                "theme_id": null
              },
              {
                "id": 5802,
                "content": "A run of bad weather delayed the work.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "runs",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          },
          {
            "id": 59,
            "word_id": 1001,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 591,
              "content": "a journey made regularly by a vehicle",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5901,
                "content": "The driver finished the morning [run] early.",
                "theme_id": null
              },
              {
                "id": 5902,
                "content": "This is the last bus run of the day.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "runs",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/rʌn/",
            "ipa_us": "/rʌn/"
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 1003,
        "lemma": "set",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 63,
            "word_id": 1003,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 631,
              "content": "to put something in a particular place",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6301,
                "content": "She [set|p] the glass on the table.",
                "theme_id": null
              },
              {
                "id": 6302,
                "content": "Set the box down gently.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "set",
                "inf": "BASE"
              },
              {
                "surface": "set",
                "inf": "PAST"
              },
              {
                "surface": "set",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "sets",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "setting",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/set/",
            "ipa_us": "/set/"
          },
          {
            "id": 64,
            "word_id": 1003,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 641,
              "content": "to decide or establish a rule, goal, or standard",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6401,
                "content": "We [set|p] a clear deadline.",
                "theme_id": null
              },
              {
                "id": 6402,
                "content": "The teacher sets the rules.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "set",
                "inf": "BASE"
              },
              {
                "surface": "set",
                "inf": "PAST"
              },
              {
                "surface": "set",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "sets",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "setting",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [
              "set a goal",
              "set a limit"
            ],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": "/set/",
            "ipa_us": "/set/"
          },
          {
            "id": 65,
            "word_id": 1003,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 651,
              "content": "to adjust a device to a particular setting",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6501,
                "content": "Please [set] the alarm for six.",
                "theme_id": null
              },
              {
                "id": 6502,
                "content": "Set the oven to 180 degrees.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "set",
                "inf": "BASE"
              },
              {
                "surface": "set",
                "inf": "PAST"
              },
              {
                "surface": "set",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "sets",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "setting",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/set/",
            "ipa_us": "/set/"
          },
          {
            "id": 66,
            "word_id": 1003,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 661,
              "content": "to become firm or solid",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6601,
                "content": "Leave the paint to [set] overnight.",
                "theme_id": null
              },
              {
                "id": 6602,
                "content": "The jelly sets in the fridge.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "set",
                "inf": "BASE"
              },
              {
                "surface": "set",
                "inf": "PAST"
              },
              {
                "surface": "set",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "sets",
                "inf": "PRESENT_3SG"
              },
              {
                "surface": "setting",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/set/",
            "ipa_us": "/set/"
          },
          {
            "id": 67,
            "word_id": 1003,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 671,
              "content": "a group of things that belong together",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6701,
                "content": "She bought a [set] of six cups.",
                "theme_id": null
              },
              {
                "id": 6702,
                "content": "The box contains a set of tools.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "sets",
                "inf": "PLURAL"
              }
            ],
            "patterns": [
              "a set of {sth}"
            ],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/set/",
            "ipa_us": "/set/"
          },
          {
            "id": 68,
            "word_id": 1003,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 681,
              "content": "one part of a tennis match",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6801,
                "content": "He won the first [set].",
                "theme_id": null
              },
              {
                "id": 6802,
                "content": "The match went to a final set.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "sets",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": "/set/",
            "ipa_us": "/set/"
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 1004,
        "lemma": "light",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 69,
            "word_id": 1004,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 691,
              "content": "the brightness that makes it possible to see",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6901,
                "content": "The morning [light] filled the room.",
                "theme_id": null
              },
              {
                "id": 6902,
                "content": "There was not enough light to read.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A1",
            "register": null,
            "ipa_uk": "/laɪt/",
            "ipa_us": "/laɪt/"
          },
          {
            "id": 70,
            "word_id": 1004,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 701,
              "content": "a lamp or other object that produces light",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7001,
                "content": "Please turn off the [light].",
                "theme_id": null
              },
              {
                "id": 7002,
                "content": "The street lights came on at dusk.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "lights",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A1",
            "register": null,
            "ipa_uk": "/laɪt/",
            "ipa_us": "/laɪt/"
          },
          {
            "id": 71,
            "word_id": 1004,
            "pos": "ADJECTIVE",
            "tier": "COMMON",
            "definition": {
              "id": 711,
              "content": "not heavy in weight",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7101,
                "content": "This bag is surprisingly [light].",
                "theme_id": null
              },
              {
                "id": 7102,
                "content": "Wear light shoes for the walk.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "lighter",
                "inf": "COMPARATIVE"
              },
              {
                "surface": "lightest",
                "inf": "SUPERLATIVE"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [
              {
                "rel_type": "ANTONYM",
                "to_word_id": 1006,
                "to_word_lemma": "heavy",
                "resolution_state": "RESOLVED",
                "to_sense_id": 76
              }
            ],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/laɪt/",
            "ipa_us": "/laɪt/"
          },
          {
            "id": 72,
            "word_id": 1004,
            "pos": "ADJECTIVE",
            "tier": "COMMON",
            "definition": {
              "id": 721,
              "content": "pale in color or shade",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7201,
                "content": "She chose a [light] blue shirt.",
                "theme_id": null
              },
              {
                "id": 7202,
                "content": "The walls are a light grey.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "lighter",
                "inf": "COMPARATIVE"
              },
              {
                "surface": "lightest",
                "inf": "SUPERLATIVE"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/laɪt/",
            "ipa_us": "/laɪt/"
          },
          {
            "id": 73,
            "word_id": 1004,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 731,
              "content": "to make something start burning or give light",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7301,
                "content": "He [lit|p] a candle.",
                "theme_id": null
              },
              {
                "id": 7302,
                "content": "They lit the fire before sunset.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "lit",
                "inf": "PAST"
              },
              {
                "surface": "lit",
                "inf": "PAST_PARTICIPLE"
              },
              {
                "surface": "lighting",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": "/laɪt/",
            "ipa_us": "/laɪt/"
          }
        ],
        "aliases": [],
        "related": [
          {
            "rel_type": "ANTONYM",
            "to_word_id": 1006,
            "to_word_lemma": "heavy"
          }
        ]
      },
      {
        "id": 1005,
        "lemma": "color",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 74,
            "word_id": 1005,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 741,
              "content": "the appearance of something caused by reflected light",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7401,
                "content": "What [color] is the door?",
                "theme_id": null
              },
              {
                "id": 7402,
                "content": "The leaves changed color in autumn.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "colors",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A1",
            "register": null,
            "ipa_uk": "/ˈkʌlə/",
            "ipa_us": "/ˈkʌlər/"
          },
          {
            "id": 75,
            "word_id": 1005,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 751,
              "content": "to add color to a drawing or surface",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7501,
                "content": "The children [colored|p] the picture.",
                "theme_id": null
              },
              {
                "id": 7502,
                "content": "You can color the map with pencils.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "colored",
                "inf": "PAST"
              },
              {
                "surface": "coloring",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/ˈkʌlə/",
            "ipa_us": "/ˈkʌlər/"
          }
        ],
        "aliases": [
          "colour"
        ],
        "related": []
      },
      {
        "id": 1006,
        "lemma": "heavy",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 76,
            "word_id": 1006,
            "pos": "ADJECTIVE",
            "tier": "COMMON",
            "definition": {
              "id": 761,
              "content": "weighing a lot",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7601,
                "content": "This suitcase is too [heavy] to lift.",
                "theme_id": null
              },
              {
                "id": 7602,
                "content": "The box took two people to move.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "heavier",
                "inf": "COMPARATIVE"
              },
              {
                "surface": "heaviest",
                "inf": "SUPERLATIVE"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [
              {
                "rel_type": "ANTONYM",
                "to_word_id": 1004,
                "to_word_lemma": "light",
                "resolution_state": "RESOLVED",
                "to_sense_id": 71
              }
            ],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/ˈhevi/",
            "ipa_us": "/ˈhevi/"
          }
        ],
        "aliases": [],
        "related": [
          {
            "rel_type": "ANTONYM",
            "to_word_id": 1004,
            "to_word_lemma": "light"
          }
        ]
      },
      {
        "id": 2001,
        "lemma": "agenda",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 1,
            "word_id": 2001,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 11,
              "content": "a list of matters to discuss at a meeting",
              "theme_id": null
            },
            "examples": [
              {
                "id": 101,
                "content": "We added the budget to the [agenda].",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2002,
        "lemma": "allocate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 2,
            "word_id": 2002,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 21,
              "content": "to give something to a person or purpose",
              "theme_id": null
            },
            "examples": [
              {
                "id": 201,
                "content": "We [allocated|p] more time to the discussion.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2003,
        "lemma": "approach",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 3,
            "word_id": 2003,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 31,
              "content": "a way of dealing with a situation or problem",
              "theme_id": null
            },
            "examples": [
              {
                "id": 301,
                "content": "We need a different [approach] to this project.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          },
          {
            "id": 77,
            "word_id": 2003,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 771,
              "content": "to move closer to someone or something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7701,
                "content": "The train [approached|p] the station.",
                "theme_id": null
              },
              {
                "id": 7702,
                "content": "She approached the desk.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2004,
        "lemma": "collaborate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 4,
            "word_id": 2004,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 41,
              "content": "to work together to achieve something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 401,
                "content": "The two teams [collaborated|p] on the proposal.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2005,
        "lemma": "constraint",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 5,
            "word_id": 2005,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 51,
              "content": "something that limits what you can do",
              "theme_id": null
            },
            "examples": [
              {
                "id": 501,
                "content": "Time is our main [constraint].",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "C1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2006,
        "lemma": "delegate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 6,
            "word_id": 2006,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 61,
              "content": "to give a task or responsibility to someone else",
              "theme_id": null
            },
            "examples": [
              {
                "id": 601,
                "content": "She [delegated|p] the research to her colleague.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2007,
        "lemma": "feedback",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 7,
            "word_id": 2007,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 71,
              "content": "information about how well someone has done something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 701,
                "content": "Your [feedback] helped us improve the design.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2008,
        "lemma": "negotiate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 8,
            "word_id": 2008,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 81,
              "content": "to discuss something in order to reach an agreement",
              "theme_id": null
            },
            "examples": [
              {
                "id": 801,
                "content": "They [negotiated|p] a new delivery date.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2009,
        "lemma": "objective",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 9,
            "word_id": 2009,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 91,
              "content": "something you are trying to achieve",
              "theme_id": null
            },
            "examples": [
              {
                "id": 901,
                "content": "Our [objective] is to make the process simpler.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2010,
        "lemma": "proposal",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 10,
            "word_id": 2010,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 101,
              "content": "a suggested plan for others to consider",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1001,
                "content": "We will discuss your [proposal] on Monday.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2011,
        "lemma": "deadline",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 11,
            "word_id": 2011,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 111,
              "content": "the latest time by which something must be completed",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1101,
                "content": "The [deadline] for the report is Friday.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2012,
        "lemma": "consensus",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 12,
            "word_id": 2012,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 121,
              "content": "an opinion or decision that everyone in a group agrees with",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1201,
                "content": "The group reached a [consensus] after the discussion.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "C1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2013,
        "lemma": "acknowledge",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 13,
            "word_id": 2013,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 131,
              "content": "to show that you have received or noticed something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1301,
                "content": "Please [acknowledge] receipt of this message.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2014,
        "lemma": "clarify",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 14,
            "word_id": 2014,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 141,
              "content": "to make something easier to understand",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1401,
                "content": "Could you [clarify] the final requirement?",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2015,
        "lemma": "confirm",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 15,
            "word_id": 2015,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 151,
              "content": "to state that something is correct or definite",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1501,
                "content": "I am writing to [confirm] our appointment.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2016,
        "lemma": "correspondence",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 16,
            "word_id": 2016,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 161,
              "content": "letters or messages exchanged between people",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1601,
                "content": "Keep a copy of all [correspondence].",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "C1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2017,
        "lemma": "enquiry",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 17,
            "word_id": 2017,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 171,
              "content": "a request for information",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1701,
                "content": "Thank you for your [enquiry] about the course.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2018,
        "lemma": "forward",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 18,
            "word_id": 2018,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 181,
              "content": "to send a message you received to another person",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1801,
                "content": "Could you [forward] the details to me?",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          },
          {
            "id": 81,
            "word_id": 2018,
            "pos": "ADVERB",
            "tier": "COMMON",
            "definition": {
              "id": 811,
              "content": "toward a position in front",
              "theme_id": null
            },
            "examples": [
              {
                "id": 8101,
                "content": "He stepped [forward].",
                "theme_id": null
              },
              {
                "id": 8102,
                "content": "Please move forward a little.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2019,
        "lemma": "regarding",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 19,
            "word_id": 2019,
            "pos": "PREPOSITION",
            "tier": "COMMON",
            "definition": {
              "id": 191,
              "content": "about a particular subject",
              "theme_id": null
            },
            "examples": [
              {
                "id": 1901,
                "content": "I have a question [regarding] the schedule.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2020,
        "lemma": "recipient",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 20,
            "word_id": 2020,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 201,
              "content": "a person who receives something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2001,
                "content": "Check the [recipient] before sending the email.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2021,
        "lemma": "request",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 21,
            "word_id": 2021,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 211,
              "content": "an act of asking for something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2101,
                "content": "We received a [request] for more information.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          },
          {
            "id": 78,
            "word_id": 2021,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 781,
              "content": "to ask formally for something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7801,
                "content": "They [requested|p] more information.",
                "theme_id": null
              },
              {
                "id": 7802,
                "content": "You can request a copy.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": "FORMAL",
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": [
          {
            "rel_type": "RELATED",
            "to_word_id": 2017,
            "to_word_lemma": "enquiry"
          }
        ]
      },
      {
        "id": 2022,
        "lemma": "respond",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 22,
            "word_id": 2022,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 221,
              "content": "to give an answer or react to something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2201,
                "content": "We will [respond] to your message tomorrow.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2023,
        "lemma": "attach",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 23,
            "word_id": 2023,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 231,
              "content": "to include a file with an electronic message",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2301,
                "content": "I have [attached|pp] the updated document.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2024,
        "lemma": "follow up",
        "type": "PHRASAL_VERB",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 24,
            "word_id": 2024,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 241,
              "content": "to take further action after an earlier event",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2401,
                "content": "I will [follow up] with the team next week.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2025,
        "lemma": "demonstrate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 25,
            "word_id": 2025,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 251,
              "content": "to show how something works or is done",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2501,
                "content": "Let me [demonstrate] the new feature.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2026,
        "lemma": "emphasize",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 26,
            "word_id": 2026,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 261,
              "content": "to give special importance to something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2601,
                "content": "She [emphasized|p] the need for clear communication.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2027,
        "lemma": "illustrate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 27,
            "word_id": 2027,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 271,
              "content": "to make an idea clear by giving an example",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2701,
                "content": "This example [illustrates|3] the problem.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2028,
        "lemma": "outline",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 28,
            "word_id": 2028,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 281,
              "content": "to describe the main facts or ideas of something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2801,
                "content": "I will [outline] the plan before we begin.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          },
          {
            "id": 80,
            "word_id": 2028,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 801,
              "content": "a brief description of the main points",
              "theme_id": null
            },
            "examples": [
              {
                "id": 8001,
                "content": "The report begins with an [outline].",
                "theme_id": null
              },
              {
                "id": 8002,
                "content": "She gave us a short outline.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2029,
        "lemma": "summarize",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 29,
            "word_id": 2029,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 291,
              "content": "to express the most important facts in a short form",
              "theme_id": null
            },
            "examples": [
              {
                "id": 2901,
                "content": "Could you [summarize] the main findings?",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2030,
        "lemma": "implement",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 30,
            "word_id": 2030,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 301,
              "content": "to put a plan or decision into effect",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3001,
                "content": "We will [implement] the changes next month.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2031,
        "lemma": "evaluate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 31,
            "word_id": 2031,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 311,
              "content": "to judge the quality or value of something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3101,
                "content": "We [evaluated|p] several possible solutions.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2032,
        "lemma": "coordinate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 32,
            "word_id": 2032,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 321,
              "content": "to organize people or activities so they work well together",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3201,
                "content": "She [coordinates|3] the work of three teams.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2033,
        "lemma": "resolve",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 33,
            "word_id": 2033,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 331,
              "content": "to find a solution to a problem or disagreement",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3301,
                "content": "We [resolved|p] the issue before the meeting.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2034,
        "lemma": "prioritize",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 34,
            "word_id": 2034,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 341,
              "content": "to decide which tasks are most important",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3401,
                "content": "We need to [prioritize] the urgent requests.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2035,
        "lemma": "maintain",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 35,
            "word_id": 2035,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 351,
              "content": "to keep something in good condition or at the same level",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3501,
                "content": "We [maintain] a shared list of decisions.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2036,
        "lemma": "contribute",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 36,
            "word_id": 2036,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 361,
              "content": "to give something to help achieve a shared purpose",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3601,
                "content": "Everyone [contributed|p] an idea.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2037,
        "lemma": "consider",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 37,
            "word_id": 2037,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 371,
              "content": "to think carefully about something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3701,
                "content": "Take some time to [consider] the options.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2038,
        "lemma": "appreciate",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 38,
            "word_id": 2038,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 381,
              "content": "to be grateful for something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3801,
                "content": "I [appreciate] your help.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2039,
        "lemma": "suggest",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 39,
            "word_id": 2039,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 391,
              "content": "to offer an idea for someone to consider",
              "theme_id": null
            },
            "examples": [
              {
                "id": 3901,
                "content": "What would you [suggest] for lunch?",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": [
          {
            "rel_type": "RELATED",
            "to_word_id": 2043,
            "to_word_lemma": "recommend"
          }
        ]
      },
      {
        "id": 2040,
        "lemma": "arrange",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 40,
            "word_id": 2040,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 401,
              "content": "to make plans for something to happen",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4001,
                "content": "We [arranged|p] to meet after work.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2041,
        "lemma": "notice",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 41,
            "word_id": 2041,
            "pos": "VERB",
            "tier": "CORE",
            "definition": {
              "id": 411,
              "content": "to become aware of something",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4101,
                "content": "Did you [notice] the change?",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          },
          {
            "id": 79,
            "word_id": 2041,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 791,
              "content": "a written announcement or warning",
              "theme_id": null
            },
            "examples": [
              {
                "id": 7901,
                "content": "A [notice] was posted on the door.",
                "theme_id": null
              },
              {
                "id": 7902,
                "content": "You must give a month of notice.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2042,
        "lemma": "prefer",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 42,
            "word_id": 2042,
            "pos": "VERB",
            "tier": "CORE",
            "definition": {
              "id": 421,
              "content": "to like one thing more than another",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4201,
                "content": "I [prefer] to walk when the weather is good.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2043,
        "lemma": "recommend",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 43,
            "word_id": 2043,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 431,
              "content": "to say that something is good or useful",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4301,
                "content": "Can you [recommend] a good book?",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": [
          {
            "rel_type": "RELATED",
            "to_word_id": 2039,
            "to_word_lemma": "suggest"
          }
        ]
      },
      {
        "id": 2044,
        "lemma": "realize",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 44,
            "word_id": 2044,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 441,
              "content": "to understand something that you did not understand before",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4401,
                "content": "I [realized|p] I had left my keys at home.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2045,
        "lemma": "wonder",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 45,
            "word_id": 2045,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 451,
              "content": "to think about something because you want to know more",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4501,
                "content": "I [wonder] how long the journey will take.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2046,
        "lemma": "expect",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 46,
            "word_id": 2046,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 461,
              "content": "to think that something is likely to happen",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4601,
                "content": "We [expect] the train to arrive soon.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B1",
            "register": null,
            "ipa_uk": null,
            "ipa_us": null
          }
        ],
        "aliases": [],
        "related": []
      },
      {
        "id": 2047,
        "lemma": "bank",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 47,
            "word_id": 2047,
            "pos": "NOUN",
            "tier": "CORE",
            "definition": {
              "id": 471,
              "content": "an organization where people keep or borrow money",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4701,
                "content": "She deposited the money at the [bank].",
                "theme_id": null
              },
              {
                "id": 4702,
                "content": "The [bank] approved their loan.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "banks",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [
              "open a bank account",
              "bank loan"
            ],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/bæŋk/",
            "ipa_us": "/bæŋk/"
          },
          {
            "id": 48,
            "word_id": 2047,
            "pos": "NOUN",
            "tier": "CORE",
            "definition": {
              "id": 481,
              "content": "the land along the side of a river",
              "theme_id": null
            },
            "examples": [
              {
                "id": 4801,
                "content": "They sat on the river [bank].",
                "theme_id": null
              },
              {
                "id": 4802,
                "content": "Wildflowers grew along the [bank].",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "banks",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "A2",
            "register": null,
            "ipa_uk": "/bæŋk/",
            "ipa_us": "/bæŋk/"
          },
          {
            "id": 60,
            "word_id": 2047,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 601,
              "content": "to put money into a bank account",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6001,
                "content": "I [banked|p] the cheque.",
                "theme_id": null
              },
              {
                "id": 6002,
                "content": "She banks her wages every Friday.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "banked",
                "inf": "PAST"
              },
              {
                "surface": "banking",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/bæŋk/",
            "ipa_us": "/bæŋk/"
          },
          {
            "id": 61,
            "word_id": 2047,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 611,
              "content": "a supply or collection kept for future use",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6101,
                "content": "The hospital maintains a blood [bank].",
                "theme_id": null
              },
              {
                "id": 6102,
                "content": "The archive is a useful bank of images.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "banks",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/bæŋk/",
            "ipa_us": "/bæŋk/"
          },
          {
            "id": 62,
            "word_id": 2047,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 621,
              "content": "to rely on something happening",
              "theme_id": null
            },
            "examples": [
              {
                "id": 6201,
                "content": "We are [banking|ing] on good weather.",
                "theme_id": null
              },
              {
                "id": 6202,
                "content": "Do not bank on the train arriving early.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "banked",
                "inf": "PAST"
              },
              {
                "surface": "banking",
                "inf": "ING"
              }
            ],
            "patterns": [
              "bank on {sth}"
            ],
            "collocations": [],
            "relations": [],
            "cefr_level": "C1",
            "register": null,
            "ipa_uk": "/bæŋk/",
            "ipa_us": "/bæŋk/"
          }
        ],
        "aliases": [],
        "related": []
      }
    ],
    "references": [
      {
        "reference_id": "preview-orbit",
        "display": "orbit",
        "entry_type": "WORD"
      }
    ],
    "pending_words": [
      {
        "id": 1002,
        "lemma": "orbit",
        "type": "WORD",
        "generation_state": "DONE",
        "senses": [
          {
            "id": 52,
            "word_id": 1002,
            "pos": "NOUN",
            "tier": "COMMON",
            "definition": {
              "id": 521,
              "content": "the curved path of an object around a planet or star",
              "theme_id": null
            },
            "examples": [
              {
                "id": 5201,
                "content": "The satellite entered [orbit].",
                "theme_id": null
              },
              {
                "id": 5202,
                "content": "The moon stays in [orbit] around Earth.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "orbits",
                "inf": "PLURAL"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/ˈɔːbɪt/",
            "ipa_us": "/ˈɔːrbɪt/"
          },
          {
            "id": 82,
            "word_id": 1002,
            "pos": "VERB",
            "tier": "COMMON",
            "definition": {
              "id": 821,
              "content": "to travel around a planet, star, or other object",
              "theme_id": null
            },
            "examples": [
              {
                "id": 8201,
                "content": "The satellite [orbits|3] Earth.",
                "theme_id": null
              },
              {
                "id": 8202,
                "content": "Several moons orbit the planet.",
                "theme_id": null
              }
            ],
            "forms": [
              {
                "surface": "orbited",
                "inf": "PAST"
              },
              {
                "surface": "orbiting",
                "inf": "ING"
              }
            ],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "B2",
            "register": null,
            "ipa_uk": "/ˈɔːbɪt/",
            "ipa_us": "/ˈɔːrbɪt/"
          },
          {
            "id": 83,
            "word_id": 1002,
            "pos": "NOUN",
            "tier": "LESS_COMMON",
            "definition": {
              "id": 831,
              "content": "the usual area or range of influence",
              "theme_id": null
            },
            "examples": [
              {
                "id": 8301,
                "content": "The company fell into the group’s [orbit].",
                "theme_id": null
              },
              {
                "id": 8302,
                "content": "The issue was outside her orbit.",
                "theme_id": null
              }
            ],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": [],
            "cefr_level": "C1",
            "register": "FORMAL",
            "ipa_uk": "/ˈɔːbɪt/",
            "ipa_us": "/ˈɔːrbɪt/"
          }
        ],
        "aliases": [],
        "related": []
      }
    ]
  }
}

export default database
