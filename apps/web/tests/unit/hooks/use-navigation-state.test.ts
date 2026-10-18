// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useNavigationState } from '@/components/shell/use-navigation-state.client'
import { useAiPanelState } from '@/features/assistant/use-panel-state.client'
import { aiOpenKey, navigationCollapsedKey } from '@/lib/preferences/browser'

const flushMutationObserver = () => new Promise(resolve => setTimeout(resolve, 0))

describe('useNavigationState', () => {
  beforeEach(() => {
    delete document.documentElement.dataset.navigationCollapsed
    localStorage.clear()
  })

  afterEach(() => {
    delete document.documentElement.dataset.navigationCollapsed
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('subscribes to external store and provides initial snapshot', () => {
    const { result } = renderHook(() => useNavigationState())
    expect(result.current.collapsed).toBe(false)

    document.documentElement.dataset.navigationCollapsed = 'true'
    const { result: preloadedResult } = renderHook(() => useNavigationState())
    expect(preloadedResult.current.collapsed).toBe(true)
  })

  it('toggles collapsed state, updates DOM dataset and persists to localStorage', async () => {
    const { result } = renderHook(() => useNavigationState())

    await act(async () => {
      result.current.toggleCollapsed()
      await flushMutationObserver()
    })

    expect(result.current.collapsed).toBe(true)
    expect(document.documentElement.dataset.navigationCollapsed).toBe('true')
    expect(localStorage.getItem(navigationCollapsedKey)).toBe('true')

    await act(async () => {
      result.current.toggleCollapsed()
      await flushMutationObserver()
    })

    expect(result.current.collapsed).toBe(false)
    expect(document.documentElement.dataset.navigationCollapsed).toBe('false')
    expect(localStorage.getItem(navigationCollapsedKey)).toBe('false')
  })

  it('reacts to dataset mutation observer when attribute changes externally', async () => {
    const { result } = renderHook(() => useNavigationState())
    expect(result.current.collapsed).toBe(false)

    await act(async () => {
      document.documentElement.dataset.navigationCollapsed = 'true'
      await flushMutationObserver()
    })

    expect(result.current.collapsed).toBe(true)
  })

  it('synchronizes state when receiving storage events from other tabs', async () => {
    const { result } = renderHook(() => useNavigationState())
    expect(result.current.collapsed).toBe(false)

    await act(async () => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: navigationCollapsedKey,
          newValue: 'true',
        }),
      )
      await flushMutationObserver()
    })

    expect(document.documentElement.dataset.navigationCollapsed).toBe('true')
    expect(result.current.collapsed).toBe(true)

    // Clear event (key === null) should default to false
    await act(async () => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: null,
          newValue: null,
        }),
      )
      await flushMutationObserver()
    })

    expect(document.documentElement.dataset.navigationCollapsed).toBe('false')
    expect(result.current.collapsed).toBe(false)
  })

  it('gracefully falls back when localStorage throws an error', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })

    const { result } = renderHook(() => useNavigationState())

    await act(async () => {
      expect(() => {
        result.current.toggleCollapsed()
      }).not.toThrow()
      await flushMutationObserver()
    })

    expect(result.current.collapsed).toBe(true)
    expect(document.documentElement.dataset.navigationCollapsed).toBe('true')
  })
})

describe('useAiPanelState', () => {
  beforeEach(() => {
    delete document.documentElement.dataset.aiOpen
    localStorage.clear()
  })

  afterEach(() => {
    delete document.documentElement.dataset.aiOpen
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('subscribes to external store and provides initial snapshot', () => {
    const { result } = renderHook(() => useAiPanelState())
    expect(result.current.open).toBe(false)

    document.documentElement.dataset.aiOpen = 'true'
    const { result: openResult } = renderHook(() => useAiPanelState())
    expect(openResult.current.open).toBe(true)
  })

  it('setOpen updates open state, DOM dataset and localStorage', async () => {
    const { result } = renderHook(() => useAiPanelState())

    await act(async () => {
      result.current.setOpen(true)
      await flushMutationObserver()
    })

    expect(result.current.open).toBe(true)
    expect(document.documentElement.dataset.aiOpen).toBe('true')
    expect(localStorage.getItem(aiOpenKey)).toBe('true')

    await act(async () => {
      result.current.setOpen(false)
      await flushMutationObserver()
    })

    expect(result.current.open).toBe(false)
    expect(document.documentElement.dataset.aiOpen).toBe('false')
    expect(localStorage.getItem(aiOpenKey)).toBe('false')
  })

  it('toggle flips open state', async () => {
    const { result } = renderHook(() => useAiPanelState())
    expect(result.current.open).toBe(false)

    await act(async () => {
      result.current.toggle()
      await flushMutationObserver()
    })
    expect(result.current.open).toBe(true)
    expect(document.documentElement.dataset.aiOpen).toBe('true')

    await act(async () => {
      result.current.toggle()
      await flushMutationObserver()
    })
    expect(result.current.open).toBe(false)
    expect(document.documentElement.dataset.aiOpen).toBe('false')
  })

  it('reacts to dataset mutation observer on data-ai-open', async () => {
    const { result } = renderHook(() => useAiPanelState())
    expect(result.current.open).toBe(false)

    await act(async () => {
      document.documentElement.dataset.aiOpen = 'true'
      await flushMutationObserver()
    })

    expect(result.current.open).toBe(true)
  })

  it('synchronizes via storage event from other tabs', async () => {
    const { result } = renderHook(() => useAiPanelState())
    expect(result.current.open).toBe(false)

    await act(async () => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: aiOpenKey,
          newValue: 'true',
        }),
      )
      await flushMutationObserver()
    })

    expect(document.documentElement.dataset.aiOpen).toBe('true')
    expect(result.current.open).toBe(true)
  })

  it('handles localStorage errors gracefully in setOpen', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })

    const { result } = renderHook(() => useAiPanelState())

    await act(async () => {
      expect(() => {
        result.current.setOpen(true)
      }).not.toThrow()
      await flushMutationObserver()
    })

    expect(result.current.open).toBe(true)
    expect(document.documentElement.dataset.aiOpen).toBe('true')
  })
})
