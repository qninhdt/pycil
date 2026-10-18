// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useCopyToClipboard } from '@/lib/use-copy-to-clipboard.client'

describe('useCopyToClipboard', () => {
  let writeTextMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.useFakeTimers()
    writeTextMock = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: writeTextMock,
      },
      configurable: true,
      writable: true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('successfully copies text and reverts state after default duration', async () => {
    const { result } = renderHook(() => useCopyToClipboard())

    expect(result.current.isCopied).toBe(false)

    let copyPromise: Promise<boolean>
    await act(async () => {
      copyPromise = result.current.copyToClipboard('hello world')
    })

    expect(writeTextMock).toHaveBeenCalledWith('hello world')
    const success = await copyPromise!
    expect(success).toBe(true)
    expect(result.current.isCopied).toBe(true)

    // Advance time before duration expires
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(result.current.isCopied).toBe(true)

    // Advance past copiedDuration (3000ms)
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.isCopied).toBe(false)
  })

  it('respects custom copiedDuration option', async () => {
    const { result } = renderHook(() => useCopyToClipboard({ copiedDuration: 1000 }))

    await act(async () => {
      await result.current.copyToClipboard('quick copy')
    })
    expect(result.current.isCopied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(result.current.isCopied).toBe(false)
  })

  it('resets timer if copied again before previous timer expires', async () => {
    const { result } = renderHook(() => useCopyToClipboard({ copiedDuration: 2000 }))

    await act(async () => {
      await result.current.copyToClipboard('first')
    })
    expect(result.current.isCopied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(result.current.isCopied).toBe(true)

    // Copy again at 1500ms
    await act(async () => {
      await result.current.copyToClipboard('second')
    })
    expect(result.current.isCopied).toBe(true)

    // Advance another 1500ms (total 3000ms from start, 1500ms from second copy)
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    // Still true because second timer hasn't expired (2000ms duration)
    expect(result.current.isCopied).toBe(true)

    // Advance remaining 500ms
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current.isCopied).toBe(false)
  })

  it('clears timeout on teardown / unmount', async () => {
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout')
    const { result, unmount } = renderHook(() => useCopyToClipboard())

    await act(async () => {
      await result.current.copyToClipboard('teardown-test')
    })
    expect(result.current.isCopied).toBe(true)

    unmount()
    expect(clearTimeoutSpy).toHaveBeenCalled()
  })

  it('guards against race condition when component unmounts while writeText is pending', async () => {
    let resolveWriteText!: () => void
    writeTextMock.mockImplementation(
      () =>
        new Promise<void>(resolve => {
          resolveWriteText = resolve
        }),
    )

    const { result, unmount } = renderHook(() => useCopyToClipboard())

    let copyPromise!: Promise<boolean>
    act(() => {
      copyPromise = result.current.copyToClipboard('pending-text')
    })

    // Unmount before promise resolves (increments scopeGenerationRef)
    unmount()

    let outcome: boolean | undefined
    await act(async () => {
      resolveWriteText()
      outcome = await copyPromise
    })

    // Scope generation mismatch should return false and prevent state update
    expect(outcome).toBe(false)
  })

  it('handles clipboard write failure gracefully', async () => {
    writeTextMock.mockRejectedValue(new Error('Permission denied'))

    const { result } = renderHook(() => useCopyToClipboard())

    let success: boolean | undefined
    await act(async () => {
      success = await result.current.copyToClipboard('failing-text')
    })

    expect(success).toBe(false)
    expect(result.current.isCopied).toBe(false)
  })

  it('returns false immediately when value is empty or clipboard is missing', async () => {
    const { result } = renderHook(() => useCopyToClipboard())

    const emptyResult = await result.current.copyToClipboard('')
    expect(emptyResult).toBe(false)
    expect(writeTextMock).not.toHaveBeenCalled()

    // Missing clipboard
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
      writable: true,
    })
    const noClipboardResult = await result.current.copyToClipboard('text')
    expect(noClipboardResult).toBe(false)
  })
})
