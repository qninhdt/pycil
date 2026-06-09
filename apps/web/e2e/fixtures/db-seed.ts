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
  const userId = process.env.E2E_TEST_USER_ID ?? "00000000-0000-0000-0000-00000000e2e1";
  const deckId = process.env.E2E_TEST_DECK_ID ?? randomUUID();
  const termValue = "ephemeral";

  // Upsert test user (role 'user', not banned, token_version 0).
  psqlFile(`
    INSERT INTO users (id, email, name, role, token_version)
    VALUES ('${userId}', 'e2e-test@pycil.local', 'E2E Test User', 'user', 0)
    ON CONFLICT (id) DO NOTHING;
  `);

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
  psqlFile(`
    INSERT INTO user_term_stats (user_id, definition_id, mastery_score, mastery_level, review_count, interval_seconds)
    VALUES ('${userId}', ${definitionId}, 1000, 0, 0, 0)
    ON CONFLICT (user_id, definition_id) DO NOTHING;
  `);

  return { userId, deckId, termId, definitionId };
}
