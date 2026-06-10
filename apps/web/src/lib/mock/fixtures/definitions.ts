// Compact vocabulary dataset for the mock seed. Each entry expands into a
// StoreTerm + StoreDefinition + StoreQuestion. Kept data-only so the seed
// builder stays small while producing a rich showcase (30-50 terms).

export interface VocabEntry {
  value: string;
  pos: string; // part of speech
  meaning: string; // canonical_meaning
  paraphrase: string;
  example: string;
  // MCQ: correct option text + 3 distractors (order randomized at build time).
  correct: string;
  distractors: [string, string, string];
}

export interface DeckSpec {
  title: string;
  description: string;
  entries: VocabEntry[];
}

export interface FolderSpec {
  title: string;
  description: string;
  decks: DeckSpec[];
}

function e(
  value: string,
  pos: string,
  meaning: string,
  paraphrase: string,
  example: string,
  correct: string,
  distractors: [string, string, string],
): VocabEntry {
  return { value, pos, meaning, paraphrase, example, correct, distractors };
}

const SAT_CORE: VocabEntry[] = [
  e("ephemeral", "adj", "Lasting for a very short time.", "Fleeting; short-lived.", "Fame can be ephemeral.", "Lasting a very short time", ["Extremely loud", "Heavily decorated", "Deeply rooted"]),
  e("ubiquitous", "adj", "Present everywhere at once.", "Found all over.", "Smartphones are ubiquitous.", "Present everywhere", ["Rarely seen", "Strictly forbidden", "Slightly damaged"]),
  e("pragmatic", "adj", "Dealing with things sensibly and realistically.", "Practical.", "A pragmatic approach to budgeting.", "Practical and realistic", ["Wildly idealistic", "Openly hostile", "Purely decorative"]),
  e("candid", "adj", "Truthful and straightforward.", "Frank; honest.", "A candid review of the film.", "Truthful and frank", ["Secretive", "Indecisive", "Exaggerated"]),
  e("meticulous", "adj", "Showing great attention to detail.", "Very careful.", "Meticulous record keeping.", "Very careful about detail", ["Reckless", "Generous", "Forgetful"]),
  e("resilient", "adj", "Able to recover quickly from difficulty.", "Tough; bouncy.", "A resilient community.", "Quick to recover", ["Easily broken", "Slow moving", "Brightly colored"]),
  e("verbose", "adj", "Using more words than needed.", "Wordy.", "A verbose explanation.", "Using too many words", ["Silent", "Concise", "Illegible"]),
  e("austere", "adj", "Severe or plain in appearance.", "Stern; bare.", "An austere room.", "Severe and plain", ["Lavish", "Cheerful", "Crowded"]),
];

const BUSINESS: VocabEntry[] = [
  e("leverage", "verb", "Use something to maximum advantage.", "Make the most of.", "Leverage your network.", "Use to maximum advantage", ["Throw away", "Hide carefully", "Slow down"]),
  e("synergy", "noun", "Combined effect greater than the sum of parts.", "Teamwork payoff.", "Synergy between teams.", "Greater combined effect", ["A solo effort", "A legal penalty", "A type of report"]),
  e("scalable", "adj", "Able to grow without losing performance.", "Grows well.", "A scalable platform.", "Able to grow efficiently", ["Fixed in size", "Easily broken", "Hard to read"]),
  e("benchmark", "noun", "A standard point of reference.", "Yardstick.", "Beat the benchmark.", "A standard reference point", ["A random guess", "A final warning", "A small bonus"]),
  e("incentive", "noun", "A thing that motivates action.", "Reward driver.", "A cash incentive.", "A motivating reward", ["A strict rule", "A long delay", "A minor flaw"]),
  e("liability", "noun", "A thing for which one is responsible; a debt.", "Obligation.", "Reduce your liabilities.", "A debt or obligation", ["A guaranteed profit", "A free gift", "A new hire"]),
  e("attrition", "noun", "Gradual reduction of staff or strength.", "Wearing down.", "High employee attrition.", "Gradual reduction", ["Rapid growth", "A bonus payment", "A merger"]),
];

const SCIENCE: VocabEntry[] = [
  e("catalyst", "noun", "Something that speeds up a change.", "Spark.", "A catalyst for reform.", "Something that speeds change", ["A heavy weight", "A slow process", "A quiet room"]),
  e("entropy", "noun", "A measure of disorder in a system.", "Disorder.", "Entropy always increases.", "A measure of disorder", ["A measure of speed", "A type of metal", "A unit of money"]),
  e("hypothesis", "noun", "A proposed explanation to be tested.", "Educated guess.", "Test the hypothesis.", "A testable explanation", ["A proven law", "A final answer", "A random fact"]),
  e("symbiosis", "noun", "Interaction between two organisms living together.", "Living together.", "Symbiosis in coral reefs.", "Two organisms living together", ["A single cell", "A type of rock", "A weather event"]),
  e("photosynthesis", "noun", "How plants make food from light.", "Light to food.", "Photosynthesis needs sunlight.", "Plants making food from light", ["Animals digesting food", "Water freezing", "Metal rusting"]),
  e("inertia", "noun", "Resistance to change in motion.", "Staying put.", "Overcome inertia.", "Resistance to motion change", ["A burst of speed", "A loud sound", "A bright light"]),
  e("velocity", "noun", "Speed in a given direction.", "Directed speed.", "Calculate the velocity.", "Speed in a direction", ["Total weight", "Surface color", "Time of day"]),
];

const EVERYDAY: VocabEntry[] = [
  e("procrastinate", "verb", "Delay doing something.", "Put off.", "Don't procrastinate.", "To delay doing something", ["To finish early", "To shout loudly", "To travel far"]),
  e("nostalgia", "noun", "Sentimental longing for the past.", "Missing old times.", "A wave of nostalgia.", "Longing for the past", ["Fear of the future", "Hunger for food", "Anger at others"]),
  e("serendipity", "noun", "Finding good things by chance.", "Happy accident.", "Pure serendipity.", "A fortunate accident", ["A planned event", "A bad mistake", "A heavy storm"]),
  e("ambivalent", "adj", "Having mixed feelings.", "Torn.", "Ambivalent about moving.", "Having mixed feelings", ["Totally certain", "Very angry", "Fast asleep"]),
  e("eloquent", "adj", "Fluent and persuasive in speech.", "Well-spoken.", "An eloquent speaker.", "Fluent and persuasive", ["Hard to hear", "Badly dressed", "Often late"]),
  e("frugal", "adj", "Sparing with money.", "Thrifty.", "A frugal lifestyle.", "Careful with money", ["Very wasteful", "Extremely tall", "Quite noisy"]),
  e("diligent", "adj", "Showing care and effort in work.", "Hardworking.", "A diligent student.", "Hardworking and careful", ["Lazy", "Forgetful", "Rude"]),
  e("obsolete", "adj", "No longer in use.", "Outdated.", "An obsolete device.", "No longer in use", ["Brand new", "Highly valued", "Very fast"]),
];

const IDIOMS: VocabEntry[] = [
  e("break the ice", "phrase", "Initiate conversation in a social setting.", "Start things off.", "A joke to break the ice.", "To start a conversation", ["To end a meeting", "To freeze water", "To win a prize"]),
  e("hit the books", "phrase", "To study hard.", "Study intensely.", "Time to hit the books.", "To study hard", ["To relax", "To throw objects", "To go shopping"]),
  e("under the weather", "phrase", "Feeling slightly ill.", "Not well.", "I'm under the weather.", "Feeling slightly ill", ["Feeling great", "Standing outside", "Running fast"]),
  e("piece of cake", "phrase", "Something very easy.", "Easy task.", "The test was a piece of cake.", "Something very easy", ["A real dessert", "A hard problem", "A long trip"]),
  e("spill the beans", "phrase", "Reveal a secret.", "Tell all.", "Don't spill the beans.", "To reveal a secret", ["To cook dinner", "To clean up", "To stay quiet"]),
];

export const SEED_FOLDERS: FolderSpec[] = [
  {
    title: "Test Prep",
    description: "High-frequency vocabulary for standardized tests.",
    decks: [
      { title: "SAT Core Words", description: "Essential SAT adjectives.", entries: SAT_CORE },
      { title: "Science Terms", description: "Key science vocabulary.", entries: SCIENCE },
    ],
  },
  {
    title: "Professional",
    description: "Vocabulary for the workplace.",
    decks: [
      { title: "Business English", description: "Common business terms.", entries: BUSINESS },
    ],
  },
  {
    title: "Daily Life",
    description: "Everyday words and expressions.",
    decks: [
      { title: "Everyday Vocabulary", description: "Useful daily words.", entries: EVERYDAY },
      { title: "Common Idioms", description: "English idioms & phrases.", entries: IDIOMS },
    ],
  },
];

// A couple of root-level decks (no folder) to exercise the root grid.
export const SEED_ROOT_DECKS: DeckSpec[] = [
  { title: "Quick Review", description: "Mixed words for fast review.", entries: SAT_CORE.slice(0, 4).concat(EVERYDAY.slice(0, 3)) },
];
