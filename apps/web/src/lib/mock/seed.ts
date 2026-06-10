// Builds the initial mock state from the vocabulary fixtures. Produces a rich
// showcase: ~6 decks across 3 folders + 1 root deck, 30-50 terms each with a
// definition + pre-baked MCQ, varied mastery states.

import { newUuid } from "./id";
import { SEED_FOLDERS, SEED_ROOT_DECKS } from "./fixtures/definitions";
import type { DeckSpec, VocabEntry } from "./fixtures/definitions";
import type {
  MockState,
  StoreDefinition,
  StoreNode,
  StoreQuestion,
  StoreTerm,
  StoreUser,
} from "./types";

// Deterministic timestamps (no Date.now at module load for SSR stability).
const BASE_TS = Date.parse("2026-05-01T09:00:00.000Z");
function tsOffset(days: number): string {
  return new Date(BASE_TS + days * 86_400_000).toISOString();
}

// Deterministic shuffle of 4 MCQ options based on a seed int, returning the
// options array + the index of the correct answer.
function placeOptions(
  entry: VocabEntry,
  seed: number,
): { options: [string, string, string, string]; correctIndex: number } {
  const all = [entry.correct, ...entry.distractors];
  // rotate by seed so the correct answer isn't always index 0
  const rot = seed % 4;
  const rotated = [...all.slice(rot), ...all.slice(0, rot)];
  const correctIndex = rotated.indexOf(entry.correct);
  return {
    options: rotated as [string, string, string, string],
    correctIndex,
  };
}

interface BuildCtx {
  nodes: Record<string, StoreNode>;
  terms: Record<number, StoreTerm>;
  definitions: Record<number, StoreDefinition>;
  questions: Record<string, StoreQuestion>;
  questionByDefinition: Record<number, string>;
  intSeed: number;
}

function nextId(ctx: BuildCtx): number {
  ctx.intSeed += 1;
  return ctx.intSeed;
}

function buildDeck(
  ctx: BuildCtx,
  spec: DeckSpec,
  parentId: string | null,
  deckIndex: number,
): void {
  const deckId = newUuid();
  const createdAt = tsOffset(deckIndex);
  ctx.nodes[deckId] = {
    id: deckId,
    type: "DECK",
    name: spec.title,
    description: spec.description,
    parent_node_id: parentId,
    visibility: "PRIVATE",
    is_starred: deckIndex % 3 === 0,
    is_pinned: deckIndex % 4 === 0,
    created_at: createdAt,
    updated_at: tsOffset(deckIndex + 5),
  };

  spec.entries.forEach((entry, i) => {
    const defId = nextId(ctx);
    const termId = nextId(ctx);
    ctx.definitions[defId] = {
      id: defId,
      canonical_meaning: entry.meaning,
      paraphrase: entry.paraphrase,
      example: entry.example,
      part_of_speech: entry.pos,
    };
    ctx.terms[termId] = {
      id: termId,
      deck_id: deckId,
      value: entry.value,
      type: entry.pos,
      position: i,
      definition_id: defId,
      created_at: createdAt,
      updated_at: createdAt,
    };
    const { options, correctIndex } = placeOptions(entry, defId);
    const qId = newUuid();
    ctx.questions[qId] = {
      id: qId,
      definition_id: defId,
      type: "MCQ",
      stem: `What does "${entry.value}" mean?`,
      options,
      correct_index: correctIndex,
      explanation: `"${entry.value}" means: ${entry.meaning}`,
      distractor_rationale: entry.distractors,
      created_at: createdAt,
    };
    ctx.questionByDefinition[defId] = qId;
  });
}

export function buildSeed(): MockState {
  const ctx: BuildCtx = {
    nodes: {},
    terms: {},
    definitions: {},
    questions: {},
    questionByDefinition: {},
    intSeed: 1000,
  };

  let deckIndex = 0;
  SEED_FOLDERS.forEach((folder, fi) => {
    const folderId = newUuid();
    ctx.nodes[folderId] = {
      id: folderId,
      type: "FOLDER",
      name: folder.title,
      description: folder.description,
      parent_node_id: null,
      visibility: "PRIVATE",
      is_starred: false,
      is_pinned: fi === 0,
      created_at: tsOffset(fi),
      updated_at: tsOffset(fi + 1),
    };
    folder.decks.forEach((deck) => {
      buildDeck(ctx, deck, folderId, deckIndex);
      deckIndex += 1;
    });
  });

  SEED_ROOT_DECKS.forEach((deck) => {
    buildDeck(ctx, deck, null, deckIndex);
    deckIndex += 1;
  });

  const user: StoreUser = {
    id: "demo-user-0000-0000-000000000001",
    email: "demo@pycil.app",
    name: "Demo User",
    image: null,
    image_url: null,
    bio: "Exploring Pycil in demo mode.",
    study_settings: {},
  };

  return {
    user,
    nodes: ctx.nodes,
    terms: ctx.terms,
    definitions: ctx.definitions,
    questions: ctx.questions,
    questionByDefinition: ctx.questionByDefinition,
    sessions: {},
    intSeed: ctx.intSeed,
  };
}
