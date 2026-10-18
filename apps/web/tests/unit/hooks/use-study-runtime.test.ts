// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useStudyRuntime } from '@/features/study/use-study-runtime.client'
import {
  createStudySession,
  saveSession,
  sessionKey,
  type StudySession,
} from '@/features/study/session'
import { preparation } from '../fixtures'

const mockAccountId = 'user-study-123'
const mockNodeId = 'deck'

const mockProfile = {
  id: mockAccountId,
  effective_learning: {},
  library_node_id: mockNodeId,
}

const mockServices = {
  dictionary: { previews: vi.fn().mockResolvedValue([]) },
  learning: {
    prepare: vi.fn(),
    grade: vi.fn(),
    review: vi.fn(),
  },
  jobs: { status: vi.fn() },
  mode: 'mock',
}

const mockAccount = {
  profile: mockProfile,
  canMutate: true,
}

const mockServicesResult = {
  services: mockServices,
  scope: 'mock',
}

const mockTranslate = (key: string) => key

const mockSearchParams = {
  get: (key: string) => {
    if (key === 'node') return mockNodeId
    if (key === 'selection') return 'auto'
    return null
  },
}

const mockRouter = { push: vi.fn() }

vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams,
}))

const mockQueryClient = {
  invalidateQueries: vi.fn(),
}

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => mockQueryClient,
}))

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslate,
}))

vi.mock('@/features/account/account.client', () => ({
  useAccount: () => mockAccount,
}))

vi.mock('@/lib/api/services/provider.client', () => ({
  useServices: () => mockServicesResult,
}))

describe('useStudyRuntime multi-tab conflict detection', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('hydrates existing session from localStorage and records initial storage snapshot', () => {
    const session = createStudySession(mockAccountId, preparation())
    saveSession(session)

    const { result } = renderHook(() => useStudyRuntime())

    expect(result.current.session).not.toBeNull()
    expect(result.current.session?.id).toBe(session.id)
    expect(result.current.error).toBe('')
  })

  it('detects multi-tab conflict during commit when localStorage returns a different timestamp/payload', () => {
    const session = createStudySession(mockAccountId, preparation())
    saveSession(session)

    const { result } = renderHook(() => useStudyRuntime())
    expect(result.current.session?.id).toBe(session.id)

    // Simulate another tab modifying the session and updating localStorage
    const otherTabSession: StudySession = {
      ...session,
      position: 1,
      updated_at: new Date(Date.now() + 5000).toISOString(),
    }
    // Tab 2 saves to localStorage
    localStorage.setItem(
      sessionKey(mockAccountId, mockNodeId),
      JSON.stringify(otherTabSession),
    )

    // Current tab attempts to commit its own update
    const currentTabNext: StudySession = {
      ...session,
      draft: 'my answer from tab 1',
    }

    let commitResult: boolean | undefined
    act(() => {
      commitResult = result.current.commit(currentTabNext)
    })

    // Conflict should be detected: commit fails and error is set
    expect(commitResult).toBe(false)
    expect(result.current.error).toBe('sessionConflictError')

    // LocalStorage should retain the other tab's data, untouched by tab 1
    const stored = JSON.parse(
      localStorage.getItem(sessionKey(mockAccountId, mockNodeId))!,
    )
    expect(stored.position).toBe(1)
  })

  it('detects multi-tab conflict during answer submission when storage changed in background', async () => {
    const session = createStudySession(mockAccountId, preparation())
    saveSession(session)

    const { result } = renderHook(() => useStudyRuntime())
    expect(result.current.session).not.toBeNull()

    // Another tab updates the session timestamp
    const externalUpdate = {
      ...session,
      updated_at: new Date(Date.now() + 10000).toISOString(),
    }
    localStorage.setItem(
      sessionKey(mockAccountId, mockNodeId),
      JSON.stringify(externalUpdate),
    )

    // Tab 1 tries to answer
    await act(async () => {
      await result.current.answer('correct')
    })

    expect(result.current.error).toBe('sessionConflictError')
  })

  it('successfully commits and updates lastSaved reference when no multi-tab conflict occurs', () => {
    const session = createStudySession(mockAccountId, preparation())
    saveSession(session)

    const { result } = renderHook(() => useStudyRuntime())

    const nextSession: StudySession = {
      ...session,
      draft: 'valid update without conflict',
    }

    let success: boolean | undefined
    act(() => {
      success = result.current.commit(nextSession)
    })

    expect(success).toBe(true)
    expect(result.current.error).toBe('')
    expect(result.current.session?.draft).toBe('valid update without conflict')

    // Second sequential commit from same tab succeeds because lastSaved was updated
    const secondUpdate: StudySession = {
      ...nextSession,
      draft: 'second sequential update',
    }
    let secondSuccess: boolean | undefined
    act(() => {
      secondSuccess = result.current.commit(secondUpdate)
    })
    expect(secondSuccess).toBe(true)
    expect(result.current.session?.draft).toBe('second sequential update')
  })

  it('sets storageError when localStorage access throws during commit', () => {
    const session = createStudySession(mockAccountId, preparation())
    saveSession(session)

    const { result } = renderHook(() => useStudyRuntime())

    // Mock localStorage to throw on setItem
    vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
      throw new Error('Storage quota exceeded')
    })

    let success: boolean | undefined
    act(() => {
      success = result.current.commit(session)
    })

    expect(success).toBe(false)
    expect(result.current.error).toBe('storageError')
  })
})
