/**
 * Database seed fixture for Playwright e2e tests.
 *
 * Connects to the running Postgres (via docker compose) and
 * inserts a test_user with a pre-enriched sample deck.
 * Idempotent: uses ON CONFLICT DO NOTHING so repeated runs
 * don't fail.
 *
 * Requires `docker compose up postgres` health before use.
 */
import { execSync } from "node:child_process";
import { randomUUID } from "node:crypto";

export interface SeededData {
  userId: string;
  deckId: string;
  termId: number;
  definitionId: number;
  questionId: string;
  correctIndex: number;
}

function psql(sql: string): string {
  const host = process.env.PG_HOST ?? "localhost";
  const port = process.env.PG_PORT ?? "5432";
  const user = process.env.POSTGRES_USER ?? "pycil";
  const db = process.env.POSTGRES_DB ?? "pycil";
  const pgPassword = process.env.POSTGRES_PASSWORD ?? "pycil";

  return execSync(
    `PGPASSWORD="${pgPassword}" psql -h "${host}" -p "${port}" -U "${user}" -d "${db}" -At -c "${sql.replace(/"/g, '\\"')}"`,
    { timeout: 15_000, encoding: "utf-8" },
  ).trim();
}

function psqlFile(content: string): void {
  const host = process.env.PG_HOST ?? "localhost";
  const port = process.env.PG_PORT ?? "5432";
  const user = process.env.POSTGRES_USER ?? "pycil";
  const db = process.env.POSTGRES_DB ?? "pycil";
  const pgPassword = process.env.POSTGRES_PASSWORD ?? "pycil";

  execSync(
    `PGPASSWORD="${pgPassword}" psql -h "${host}" -p "${port}" -U "${user}" -d "${db}" -v ON_ERROR_STOP=1`,
    { timeout: 15_000, encoding: "utf-8", input: content },
  );
}

export function seedDatabase(): SeededData {
  const email = process.env.E2E_TEST_EMAIL ?? "e2e-test@example.com";
  const deckId = process.env.E2E_TEST_DECK_ID ?? randomUUID();
  const termValue = "ephemeral";

  // Upsert the test user keyed on EMAIL — the same key core's upsert_user uses
  // on real Dex login. The id is NOT hardcoded: real login creates the row with
  // gen_random_uuid(), so a seed that pinned ...e2e1 would create a SECOND user
  // and the seeded deck would belong to a row nobody logs in as ("logged in but
  // no data"). Keying on email + reading the id back makes the seed converge on
  // whichever row login created, regardless of seed/login order.
  psqlFile(`
    INSERT INTO users (email, name, role, token_version)
    VALUES ('${email}', 'E2E Test User', 'user', 0)
    ON CONFLICT (email) DO UPDATE SET role = 'user';
  `);
  const userId = psql(`SELECT id FROM users WHERE email = '${email}'`);

  // Upsert the term, then read its id with a plain SELECT. psql -c on an
  // INSERT…RETURNING also emits the "INSERT 0 1" command tag on stdout, which
  // pollutes the captured value (→ NaN); a separate SELECT returns a clean int.
  psqlFile(`
    INSERT INTO terms (value, type)
    VALUES ('${termValue}', 'SINGLE_WORD')
    ON CONFLICT (value) DO NOTHING;
  `);
  const termId = Number(psql(`SELECT id FROM terms WHERE value = '${termValue}'`));

  // Upsert a pre-enriched definition (no LLM call needed), then SELECT its id.
  psqlFile(`
    INSERT INTO definitions (term_id, sense_index, cefr_level, part_of_speech, canonical_meaning, synonyms, antonyms, frequency)
    VALUES (${termId}, 0, 'B2', 'ADJECTIVE', 'Lasting for a very short time; transient.', ARRAY['fleeting','momentary','brief'], ARRAY['permanent','lasting','eternal'], 1)
    ON CONFLICT (term_id, sense_index) DO NOTHING;
  `);
  const definitionId = Number(
    psql(`SELECT id FROM definitions WHERE term_id = ${termId} AND sense_index = 0`),
  );

  // Upsert paraphrases.
  psqlFile(`
    INSERT INTO definition_paraphrases (definition_id, value, cefr_level)
    VALUES (${definitionId}, 'Something that fades or disappears quickly.', 'B1')
    ON CONFLICT DO NOTHING;
    INSERT INTO definition_paraphrases (definition_id, value, cefr_level)
    VALUES (${definitionId}, 'Not built to last; short-lived in nature.', 'C1')
    ON CONFLICT DO NOTHING;
  `);

  // Upsert example sentences.
  psqlFile(`
    INSERT INTO term_example_sentences (definition_id, value, cefr_level)
    VALUES (${definitionId}, 'The joy of a new purchase is often ephemeral.', 'B2')
    ON CONFLICT DO NOTHING;
    INSERT INTO term_example_sentences (definition_id, value, cefr_level)
    VALUES (${definitionId}, 'Ephemeral trends come and go with each season.', 'B2')
    ON CONFLICT DO NOTHING;
  `);

  // Create/upsert a deck node for the test user.
  psqlFile(`
    INSERT INTO nodes (id, author_id, type, name, description, visibility)
    VALUES ('${deckId}', '${userId}', 'DECK', 'E2E Starter Deck', 'Seeded deck for e2e tests', 'PRIVATE')
    ON CONFLICT (id) DO NOTHING;
    INSERT INTO deck_attributes (node_id)
    VALUES ('${deckId}')
    ON CONFLICT (node_id) DO NOTHING;
  `);

  // Link deck → term → definition.
  psqlFile(`
    INSERT INTO deck_terms (deck_id, term_id, position)
    VALUES ('${deckId}', ${termId}, 0)
    ON CONFLICT (deck_id, term_id) DO NOTHING;
    INSERT INTO deck_definitions (deck_id, definition_id, position)
    VALUES ('${deckId}', ${definitionId}, 0)
    ON CONFLICT (deck_id, definition_id) DO NOTHING;
  `);

  // Seed user_term_stats so learn/flashcard modes see ready terms.
  // next_review_date MUST be in the past (a "due" term). The selection query
  // ranks terms as due (NRD<=now) | new (no row) | upcoming (NRD>now); a row
  // with NULL NRD matches none of those branches → the term is invisible and
  // start_session 400s "no_terms_to_study". A past NRD puts it in the due
  // branch so the learn loop can actually select it. last_review_date is set
  // so the ELO time-decay factor has a real prior interval to work from.
  //
  // DO UPDATE (not DO NOTHING): the term "ephemeral" (definition_id) is shared
  // across runs, and a prior session's ELO commit leaves a mutated row behind.
  // Forcing the baseline back to score 1000 + due every seed gives each run a
  // deterministic `before` so the spec's strict-increase assertion is stable.
  psqlFile(`
    INSERT INTO user_term_stats (user_id, definition_id, mastery_score, mastery_level, review_count, interval_seconds, last_review_date, next_review_date)
    VALUES ('${userId}', ${definitionId}, 1000, 0, 0, 86400, NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day')
    ON CONFLICT (user_id, definition_id) DO UPDATE SET
      mastery_score = 1000,
      mastery_level = 0,
      review_count = 0,
      interval_seconds = 86400,
      last_review_date = NOW() - INTERVAL '2 days',
      next_review_date = NOW() - INTERVAL '1 day';
  `);

  // Seed a deterministic MCQ so the learn-loop spec can click the KNOWN-correct
  // option (index 0) without any LLM generation. Shape matches MCQData
  // (4 unique options, correct_index, explanation, 3 distractor rationales) so
  // the registry plugin's check_answer accepts it. Deterministic id lets the
  // spec read it back. ON CONFLICT keeps the seed idempotent across reruns.
  const questionId =
    process.env.E2E_TEST_QUESTION_ID ?? "00000000-0000-0000-0000-0000000c0de1";
  const correctIndex = 0;
  const mcqData = JSON.stringify({
    stem: "Which word means lasting for a very short time?",
    options: ["ephemeral", "permanent", "eternal", "perpetual"],
    correct_index: correctIndex,
    explanation: "Ephemeral means transient or short-lived.",
    distractor_rationale: [
      "Permanent means lasting indefinitely.",
      "Eternal means without end.",
      "Perpetual means continuing forever.",
    ],
  }).replace(/'/g, "''");
  psqlFile(`
    INSERT INTO questions (id, type, definition_id, data, elo)
    VALUES ('${questionId}', 'MULTIPLE_CHOICE', ${definitionId}, '${mcqData}'::jsonb, 1000)
    ON CONFLICT (id) DO NOTHING;
  `);

  return { userId, deckId, termId, definitionId, questionId, correctIndex };
}

/**
 * Read a user_term_stats row for ELO/mastery assertions. Returns null when the
 * row is absent. Used by the learn-loop spec to prove a UI answer mutated the DB.
 */
export function readUserTermStats(
  userId: string,
  definitionId: number,
): { masteryScore: number; masteryLevel: number; reviewCount: number } | null {
  const row = psql(
    `SELECT mastery_score || ',' || mastery_level || ',' || review_count ` +
      `FROM user_term_stats WHERE user_id = '${userId}' AND definition_id = ${definitionId}`,
  );
  if (!row) return null;
  const [masteryScore, masteryLevel, reviewCount] = row
    .split(",")
    .map((n) => Number(n));
  return { masteryScore, masteryLevel, reviewCount };
}

/**
 * Read a user_term_stats row by EMAIL (not id) for live specs that never
 * hardcode the user id — they let real Dex login create the row and look it up
 * by the canonical email. Mirrors readUserTermStats but resolves the id first.
 */
export function readUserTermStatsByEmail(
  email: string,
  definitionId: number,
): { userId: string; masteryScore: number; reviewCount: number } | null {
  const userId = psql(`SELECT id FROM users WHERE email = '${email}'`);
  if (!userId) return null;
  const row = psql(
    `SELECT mastery_score || ',' || review_count ` +
      `FROM user_term_stats WHERE user_id = '${userId}' AND definition_id = ${definitionId}`,
  );
  if (!row) return null;
  const [masteryScore, reviewCount] = row.split(",").map((n) => Number(n));
  return { userId, masteryScore, reviewCount };
}

/**
 * Count enriched definitions for a term — the live enrichment spec polls this
 * until the worker's generate_term job lands ≥1 definition row. Returns the
 * count plus a sample of structural fields the spec asserts on (CEFR present).
 */
export function readDefinitions(
  termId: number,
): { count: number; exampleCount: number; cefrLevels: string[] } {
  const defRows = psql(
    `SELECT id || ',' || COALESCE(cefr_level::text, '') ` +
      `FROM definitions WHERE term_id = ${termId} ORDER BY sense_index`,
  );
  if (!defRows) return { count: 0, exampleCount: 0, cefrLevels: [] };
  const lines = defRows.split("\n").filter(Boolean);
  const ids = lines.map((l) => Number(l.split(",")[0]));
  const cefrLevels = lines.map((l) => l.split(",")[1]).filter(Boolean);
  const exampleCount = Number(
    psql(
      `SELECT COUNT(*) FROM term_example_sentences ` +
        `WHERE definition_id IN (${ids.join(",")})`,
    ) || "0",
  );
  return { count: lines.length, exampleCount, cefrLevels };
}

/**
 * Read the generated question for a definition — the live MCQ spec polls this
 * to confirm the worker's generate_question job inserted a row before driving
 * the answer. Returns id, type, and (for MCQ) the correct option TEXT so the
 * spec can click the right answer without knowing the LLM-generated content
 * ahead of time. The learn loop commits ELO only after 2 correct first-attempts
 * (a wrong answer just fails to advance), so the spec must answer correctly —
 * hence reading correct_index → options[correct_index] back from the row.
 */
export function readQuestionForDefinition(
  definitionId: number,
): { id: string; type: string; correctOption: string | null } | null {
  const row = psql(
    `SELECT id || '' || type || '' || ` +
      `COALESCE(data->'options'->>(data->>'correct_index')::int, '') ` +
      `FROM questions WHERE definition_id = ${definitionId} ` +
      `ORDER BY created_at LIMIT 1`,
  );
  if (!row) return null;
  const [id, type, correctOption] = row.split("");
  return { id, type, correctOption: correctOption || null };
}

const CANONICAL_EMAIL = process.env.E2E_TEST_EMAIL ?? "e2e-test@example.com";

/** Resolve a term's id by its (unique) value; null if not yet inserted. */
export function readTermIdByValue(value: string): number | null {
  const row = psql(`SELECT id FROM terms WHERE value = '${value.replace(/'/g, "''")}'`);
  return row ? Number(row) : null;
}

/** Upsert the canonical user by email and return its id (login-created row). */
function ensureUserId(): string {
  psqlFile(`
    INSERT INTO users (email, name, role, token_version)
    VALUES ('${CANONICAL_EMAIL}', 'E2E Test User', 'user', 0)
    ON CONFLICT (email) DO UPDATE SET role = 'user';
  `);
  return psql(`SELECT id FROM users WHERE email = '${CANONICAL_EMAIL}'`);
}

export interface EmptyDeckSeed {
  userId: string;
  deckId: string;
}

/**
 * Live-enrichment seed (spec 07): the canonical user + an EMPTY deck, no term,
 * no definition. The spec adds a real term through the UI so the worker's
 * generate_term job enriches it live (stub profile returns canned definitions).
 * Deck name is unique per run so the spec can assert on it without colliding
 * with the "E2E Starter Deck" the other specs seed.
 */
export function seedEmptyDeck(): EmptyDeckSeed {
  const userId = ensureUserId();
  const deckId = process.env.E2E_LIVE_DECK_ID ?? randomUUID();
  psqlFile(`
    INSERT INTO nodes (id, author_id, type, name, description, visibility)
    VALUES ('${deckId}', '${userId}', 'DECK', 'Live Enrichment Deck', 'Live enrichment e2e', 'PRIVATE')
    ON CONFLICT (id) DO NOTHING;
    INSERT INTO deck_attributes (node_id)
    VALUES ('${deckId}')
    ON CONFLICT (node_id) DO NOTHING;
  `);
  return { userId, deckId };
}

export interface LiveLearnSeed {
  userId: string;
  deckId: string;
  termId: number;
  definitionId: number;
}

/**
 * Live-MCQ seed (spec 08): the canonical user + a deck whose term is already
 * enriched (definition + paraphrase + example — the generate_question inputs)
 * but has NO question row. So the first next_question fires real generation
 * (pending→ready; the client auto-polls) instead of serving a pre-seeded MCQ.
 *
 * Uses a DISTINCT term ("serendipity") from the seedDatabase term ("ephemeral")
 * so it never shares the pre-seeded MCQ. Any stale question for this definition
 * is deleted to guarantee the generate path runs even on a rerun. The term is
 * seeded due (past next_review_date) so term selection picks it.
 */
export function seedLiveLearnDeck(): LiveLearnSeed {
  const userId = ensureUserId();
  const deckId = process.env.E2E_LIVE_LEARN_DECK_ID ?? randomUUID();
  const termValue = "serendipity";

  psqlFile(`
    INSERT INTO terms (value, type)
    VALUES ('${termValue}', 'SINGLE_WORD')
    ON CONFLICT (value) DO NOTHING;
  `);
  const termId = Number(psql(`SELECT id FROM terms WHERE value = '${termValue}'`));

  psqlFile(`
    INSERT INTO definitions (term_id, sense_index, cefr_level, part_of_speech, canonical_meaning, synonyms, antonyms, frequency)
    VALUES (${termId}, 0, 'C1', 'NOUN', 'The occurrence of happy events by chance.', ARRAY['luck','chance','fortune'], ARRAY['misfortune'], 1)
    ON CONFLICT (term_id, sense_index) DO NOTHING;
  `);
  const definitionId = Number(
    psql(`SELECT id FROM definitions WHERE term_id = ${termId} AND sense_index = 0`),
  );

  // generate_question reads one paraphrase + one example as prompt inputs.
  psqlFile(`
    INSERT INTO definition_paraphrases (definition_id, value, cefr_level)
    VALUES (${definitionId}, 'A pleasant surprise found by accident.', 'B2')
    ON CONFLICT DO NOTHING;
    INSERT INTO term_example_sentences (definition_id, value, cefr_level)
    VALUES (${definitionId}, 'Finding that cafe was pure serendipity.', 'C1')
    ON CONFLICT DO NOTHING;
  `);

  psqlFile(`
    INSERT INTO nodes (id, author_id, type, name, description, visibility)
    VALUES ('${deckId}', '${userId}', 'DECK', 'Live MCQ Deck', 'Live MCQ generation e2e', 'PRIVATE')
    ON CONFLICT (id) DO NOTHING;
    INSERT INTO deck_attributes (node_id)
    VALUES ('${deckId}')
    ON CONFLICT (node_id) DO NOTHING;
    INSERT INTO deck_terms (deck_id, term_id, position)
    VALUES ('${deckId}', ${termId}, 0)
    ON CONFLICT (deck_id, term_id) DO NOTHING;
    INSERT INTO deck_definitions (deck_id, definition_id, position)
    VALUES ('${deckId}', ${definitionId}, 0)
    ON CONFLICT (deck_id, definition_id) DO NOTHING;
  `);

  // Due baseline so term selection picks it; reset every run for a stable
  // `before` ELO. NO question row — and drop any stale one so the learn loop
  // MUST generate the MCQ live.
  psqlFile(`
    INSERT INTO user_term_stats (user_id, definition_id, mastery_score, mastery_level, review_count, interval_seconds, last_review_date, next_review_date)
    VALUES ('${userId}', ${definitionId}, 1000, 0, 0, 86400, NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day')
    ON CONFLICT (user_id, definition_id) DO UPDATE SET
      mastery_score = 1000, mastery_level = 0, review_count = 0,
      interval_seconds = 86400,
      last_review_date = NOW() - INTERVAL '2 days',
      next_review_date = NOW() - INTERVAL '1 day';
    DELETE FROM questions WHERE definition_id = ${definitionId};
  `);

  return { userId, deckId, termId, definitionId };
}
