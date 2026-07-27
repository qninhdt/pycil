// Identity
export interface User {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  tokenVersion: number;
}

export interface Capabilities {
  assistant: boolean;
  realtime: boolean;
}

// Auth responses
export interface TokenResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  expiresIn: number;
  refreshExpiresIn: number;
}

export interface LoginStart {
  authorizeUrl: string;
}

export interface RealtimeToken {
  token: string;
  expiresAt: number;
  sseUrl: string;
}

// Hierarchy Nodes
export type NodeType = "FOLDER" | "DECK" | "REFERENCE";
export type Visibility = "PRIVATE" | "PUBLIC" | "UNLISTED";

export interface NodeItem {
  id: string;
  type: NodeType;
  name: string;
  description?: string | null;
  parentNodeId?: string | null;
  targetNodeId?: string | null;
  visibility: Visibility;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface NodePageResponse {
  items: NodeItem[];
  nextCursor?: string | null;
}

export interface NodeCreateRequest {
  type: NodeType;
  name: string;
  parentNodeId?: string | null;
  targetNodeId?: string | null;
  description?: string | null;
  visibility?: Visibility;
  confirmSubtreePublication?: boolean;
}

export interface NodeUpdateRequest {
  name?: string;
  description?: string | null;
}

export interface NodeMoveRequest {
  parentNodeId?: string | null;
}

export interface NodeVisibilityRequest {
  visibility: Visibility;
  confirmSubtreePublication?: boolean;
}

// Deck Items & Senses
export interface SenseItem {
  senseId: number;
  definition: string;
  tier: string;
  pos: string;
  cefrLevel?: string | null;
  examples: string[];
  mastery?: number; // 0-100 score
}

// Deck Settings & Subtree Items
export interface DeckSettingsRead {
  newPerBatch: number;
  reviewPerBatch: number;
}

export interface DeckSettingsUpdate {
  newPerBatch?: number;
  reviewPerBatch?: number;
}

export interface FolderItemRead {
  senseId: number;
  definition: string;
  tier: string;
  cefrLevel?: string | null;
}

export interface WeakSenseRead {
  senseId: number;
  mastery: number;
  definition?: string;
  pos?: string;
}

export type CefrDistribution = Record<string, number>;

export interface HistoryBucketRead {
  bucket: string;
  reviewed: number;
  avgMastery: number;
}

// Search & Content Acquisition
export interface WordSearchRead {
  display: string;
  entryType?: string | null;
  score: number;
  wordId?: number | null;
  cambridgeId?: number | null;
  gloss?: string | null;
  pos?: string | null;
  senses?: SenseItem[];
}

export interface GenerationCreateRead {
  taskId: string;
}

export interface SenseAddResponse {
  id: number;
  senseId: number;
}

// Study & Spaced Repetition (FSRS)
export interface SessionStartRequest {
  nodeId: string;
}

export interface SessionStartResponse {
  sessionId: string;
  nodeId: string;
  queueSize: number;
  expiresAt: string;
  firstState: "pending" | "exhausted";
}

export type QuestionFormat =
  | "definition_mcq"
  | "contextual_mcq"
  | "cloze"
  | "use_in_sentence";

export interface QuestionPayload {
  stem?: string;
  options?: string[];
  stemWithBlank?: string;
  prompt?: string;
}

export interface ReadyQuestion {
  state: "ready";
  questionId: string;
  senseId: number;
  recommendedType: QuestionFormat;
  format: QuestionFormat;
  payload: QuestionPayload;
}

export interface NextQuestionPending {
  state: "pending";
  senseId: number;
  recommendedType: QuestionFormat;
  taskId: string;
}

export interface NextQuestionExhausted {
  state: "exhausted";
}

export type NextQuestionResponse =
  | ReadyQuestion
  | NextQuestionPending
  | NextQuestionExhausted;

export interface AnswerRequest {
  sessionId: string;
  questionId: string;
  answer: string;
}

export interface GradeResponse {
  responseId: string;
  gradeStatus: "graded" | "pending";
  senseId: number;
  taskId?: string;
  isCorrect?: boolean;
  gradeScore?: number;
  gradeFeedback?: string;
  masteryBefore?: number;
  masteryAfter?: number;
}

export interface FolderStats {
  total: number;
  learned: number;
  mastered: number;
  avgMastery: number;
}

// Dashboard & Overview
export interface FSRSForecastDay {
  date: string;
  dueCount: number;
}

export interface RecentSessionInfo {
  nodeId: string;
  deckTitle: string;
  remainingCount: number;
}

export interface DashboardStatsRead {
  totalLearnedWords: number;
  dueTodayCount: number;
  masteryPercentage: number;
  fsrsForecast: FSRSForecastDay[];
  recentSession: RecentSessionInfo | null;
}

// Assistant & HITL
export interface AssistantThread {
  id: string;
  title?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export interface AssistantActionPayload {
  actionId: string;
  actionType: string;
  targetId?: string;
  description: string;
  warning?: string;
}

export interface AssistantRunEvent {
  id: number;
  sequence: number;
  eventType: "user_message" | "token" | "action" | "done" | "error";
  payload: Record<string, unknown>;
}

// Account Lifecycle & Export
export interface AccountExport {
  userId: string;
  exportedAt: string;
  profile: Record<string, unknown>;
  nodes: Record<string, unknown>[];
  senses: Record<string, unknown>[];
  stats: Record<string, unknown>[];
}
