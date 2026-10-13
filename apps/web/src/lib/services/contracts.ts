import type { AccountProfile, PublicProfile, SettingsPatch, UsageAllowance } from '../api'
import type { StudySummary, StudyActivity, ReviewSchedule, LibraryPage, PreparedSession, GradeResult, ReviewBatchResult, GradeInput, SubmittedResult, SessionSelection } from '../home-api'
import type { DataMode } from './config'
import type { LibraryDetails, ContentsOptions, MeaningOptions, MeaningPage, SourcesPage } from '../library-model'
import type { WordSearch, DictionaryWord, WordContext, WordGeneration, WordPreview } from '../dictionary-model'
import type { AssistantService } from '../assistant-api'

export type DateWindow = { start: string; end: string }
export type PrepareInput = { node_id: string; selection: SessionSelection; max_sense_count?: number; questions_per_sense?: number }

// Components and query hooks depend on this contract, never on an HTTP path or a fixture.
export interface FrontendServices {
  mode: DataMode
  notice: string | null
  assistant: AssistantService | null
  account: {
    initialProfile?: AccountProfile
    profile: (signal: AbortSignal) => Promise<AccountProfile>
    usage: (signal: AbortSignal) => Promise<UsageAllowance>
    publicProfile: (identifier: string, signal: AbortSignal) => Promise<PublicProfile>
    updateProfile: (patch: { display_name?: string; handle?: string; bio?: string | null }, signal: AbortSignal) => Promise<AccountProfile>
    updateSettings: (patch: SettingsPatch, signal: AbortSignal) => Promise<AccountProfile>
  }
  learning: {
    summary: (nodeId: string | undefined, signal: AbortSignal) => Promise<StudySummary>
    activity: (window: DateWindow, signal: AbortSignal) => Promise<StudyActivity>
    schedule: (window: DateWindow, signal: AbortSignal) => Promise<ReviewSchedule>
    prepare: (input: PrepareInput, signal: AbortSignal) => Promise<PreparedSession>
    grade: (input: GradeInput, signal: AbortSignal) => Promise<GradeResult>
    review: (input: { results: SubmittedResult[]; key: string }, signal: AbortSignal) => Promise<ReviewBatchResult>
  }
  library: {
    discovery: (options: ContentsOptions & { type?: 'deck' | 'folder'; ownerId?: string }, signal: AbortSignal) => Promise<LibraryPage>
    sources: (nodeId: string, senseId: number, cursor: string | undefined, signal: AbortSignal) => Promise<SourcesPage>
    createReference: (parentId: string, targetId: string, name: string, signal: AbortSignal, confirmPublication?: boolean) => Promise<string>
    list: (parentId: string, signal: AbortSignal) => Promise<LibraryPage>
    publicContents: (parentId: string, cursor: string | undefined, signal: AbortSignal) => Promise<LibraryPage>
    publicNode: (nodeId: string, signal: AbortSignal) => Promise<LibraryDetails>
    publicMeanings: (nodeId: string, cursor: string | undefined, signal: AbortSignal) => Promise<MeaningPage>
    details: (nodeId: string, signal: AbortSignal) => Promise<LibraryDetails>
    contents: (nodeId: string, options: ContentsOptions, signal: AbortSignal, publicRead?: boolean) => Promise<LibraryPage>
    meanings: (nodeId: string, options: MeaningOptions, signal: AbortSignal) => Promise<MeaningPage>
    updateDeckSenses: (deckId: string, change: { add: number[]; remove: number[] }, signal: AbortSignal) => Promise<void>
    createDeck: (parentId: string, name: string, senseIds: number[], signal: AbortSignal, confirmPublication?: boolean) => Promise<string>
    createNode: (input: { parentId: string; type: 'folder' | 'deck'; name: string; description: string | null; confirmPublication?: boolean }, signal: AbortSignal) => Promise<string>
    updateNode: (nodeId: string, change: { name: string; description: string | null }, signal: AbortSignal) => Promise<void>
    moveNode: (nodeId: string, parentId: string, signal: AbortSignal, publication?: { confirm: boolean; retainReference: boolean }) => Promise<void>
    copyNode: (nodeId: string, parentId: string, signal: AbortSignal, confirmPublication?: boolean) => Promise<string>
    deleteNode: (nodeId: string, signal: AbortSignal) => Promise<void>
  }
  dictionary: {
    search: (query: string, signal: AbortSignal) => Promise<WordSearch>
    word: (wordId: number, signal: AbortSignal) => Promise<DictionaryWord>
    previews: (wordIds: number[], signal: AbortSignal) => Promise<WordPreview[]>
    context: (wordId: number, signal: AbortSignal) => Promise<WordContext>
    prepare: (referenceId: string, target: string, signal: AbortSignal) => Promise<WordGeneration>
    generation: (generationId: string, signal: AbortSignal) => Promise<WordGeneration>
  }
}
