/**
 * The wire contract, as served.
 *
 * Every type here was written against a fetched `GET /v1/openapi.json`, archived
 * at `plans/260727-1332-web-frontend-rebuild/reports/v1-openapi-snapshot.json`.
 * The previous hand-authored file had drifted far enough that `tsc` passed while
 * the app targeted question formats the API no longer serves — so a green
 * typecheck here means nothing unless these types come from the document.
 *
 * Two defects in that document are worked around deliberately, both noted at
 * their definitions in ./learning:
 *
 * - The `/next` discriminator advertises `propertyName: "render_format"` while
 *   the serialized property is `renderFormat`. Pydantic emits the field name in
 *   the discriminator metadata and the alias in the body.
 * - Every `payload` is `additionalProperties: true`, so the per-format shapes are
 *   taken from the API's presentation adapter instead.
 *
 * Split by domain because one file ran well past the size this repo keeps
 * modules to. This barrel is the only public entry point: importing from
 * `@/lib/api/types` keeps working and no call site needs to know the layout.
 */

export type {
  AccountExport,
  Capabilities,
  Viewer,
} from "./auth"

export type {
  NodeAncestor,
  NodeCreate,
  NodeMove,
  NodePage,
  NodeRead,
  NodeType,
  NodeUpdate,
  NodeVisibilityUpdate,
  Visibility,
} from "./hierarchy"

export type {
  GenerationCreated,
  SenseAdded,
  SenseContent,
  SenseDetail,
  SenseForm,
  SenseReference,
  SenseRelation,
  WordSearchResult,
} from "./content"

export type {
  AnswerSubmission,
  FlashcardPayload,
  FlashcardReady,
  FreeTextPayload,
  FreeTextReady,
  GradeResult,
  InteractionMode,
  LearningSettings,
  NextQuestion,
  NextQuestionBreak,
  NextQuestionExhausted,
  NextQuestionPreparing,
  NextQuestionState,
  NextQuestionWaiting,
  ReadyQuestion,
  RenderFormat,
  Reveal,
  SessionCreated,
  SessionSenseProgress,
  SessionStart,
  SessionState,
  SingleChoicePayload,
  SingleChoiceReady,
  TextSpanPayload,
  TextSpanReady,
} from "./learning"

// Not a type: the exhaustiveness helper that makes an unhandled `/next` state a
// compile error rather than a session that silently hangs.
export { assertNever } from "./learning"

export type {
  CefrDistribution,
  DashboardStats,
  FolderItem,
  FolderStats,
  ForecastDay,
  HistoryBucket,
  RecentSession,
  WeakSense,
} from "./analytics"

export type {
  AccountCredit,
  ActionDecision,
  MessageCreate,
  ModelCatalog,
  ModelPricing,
  ModelRead,
  ResumePayload,
  Thread,
  ThreadCreate,
} from "./assistant"
