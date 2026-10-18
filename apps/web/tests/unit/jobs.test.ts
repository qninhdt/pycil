import { QueryClient, focusManager } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ApiError } from '../../src/lib/api/error'
import { parseGeneratedWord, parseJobReference, parseJobStatus, resumeJob, waitForJob, type JobStatus } from '../../src/lib/api/jobs'

// QueryObserver disables interval timers during SSR; these tests exercise browser polling.
vi.hoisted(() => { vi.stubGlobal('window', {}) })
beforeEach(() => { vi.stubGlobal('window', {}) })
const client = () => new QueryClient()
const id = '019a08b8-0000-7000-8000-000000000001'
const job = { job_id: id, status_url: `/v1/jobs/${id}` }
const status = (state: 'queued' | 'running' | 'succeeded' | 'failed', result: unknown = null) => parseJobStatus({ job_id: id, status: state, result, error: state === 'failed' ? 'job_failed' : null })
afterEach(() => { vi.useRealTimers(); focusManager.setFocused(undefined); vi.unstubAllGlobals() })

test('accepted URLs stay on the job endpoint and results are validated', () => {
  expect(parseJobReference(job)).toEqual(job)
  expect(() => parseJobReference({ ...job, status_url: 'https://foreign.test/job' })).toThrow(ApiError)
  expect(() => parseGeneratedWord({ word_id: -1 })).toThrow(ApiError)
  expect(parseGeneratedWord({ word_id: 12 })).toBe(12)
  expect(() => parseJobStatus({ job_id: id, status: ['running'], result: null, error: null })).toThrow(ApiError)
})

test('polls until success and respects Retry-After', async () => {
  vi.useFakeTimers()
  const load = vi.fn().mockResolvedValueOnce({ ...status('running'), retryAfterSeconds: 3 }).mockResolvedValue(status('succeeded', { word_id: 12 }))
  const waiting = waitForJob(client(), job, load, parseGeneratedWord, new AbortController().signal)
  await vi.advanceTimersByTimeAsync(2999)
  expect(load).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1)
  expect(await waiting).toBe(12)
})

test('backs off on outages and stops on unavailable ownership', async () => {
  vi.useFakeTimers()
  const load = vi.fn().mockRejectedValueOnce(new ApiError(503, 'job_status_unavailable')).mockRejectedValue(new ApiError(404, 'job_not_found'))
  const waiting = waitForJob(client(), job, load, parseGeneratedWord, new AbortController().signal)
  const assertion = expect(waiting).rejects.toMatchObject({ code: 'job_not_found' })
  await vi.advanceTimersByTimeAsync(2000)
  await assertion
  expect(load).toHaveBeenCalledTimes(2)
})

test('hidden screens pause interval polling and abort without cancelling the job', async () => {
  vi.useFakeTimers()
  focusManager.setFocused(false)
  const load = vi.fn().mockResolvedValue(status('queued'))
  const controller = new AbortController()
  const waiting = waitForJob(client(), job, load, parseGeneratedWord, controller.signal)
  const assertion = expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  await vi.advanceTimersByTimeAsync(10_000)
  expect(load).toHaveBeenCalledTimes(1)
  controller.abort()
  await assertion
})

test('reopening resumes its accepted reference without another submission', async () => {
  const stored = new Map([[ 'scope', JSON.stringify(job) ]])
  vi.stubGlobal('sessionStorage', { getItem: (key: string) => stored.get(key), setItem: (key: string, value: string) => stored.set(key, value), removeItem: (key: string) => stored.delete(key) })
  const submit = vi.fn()
  const load = vi.fn().mockResolvedValue(status('succeeded', { word_id: 12 }))
  expect(await resumeJob(client(), 'scope', submit, load, parseGeneratedWord, new AbortController().signal)).toBe(12)
  expect(submit).not.toHaveBeenCalled()
  expect(stored.has('scope')).toBe(false)
})

test('the waiting deadline detaches the observer and aborts its pending HTTP request', async () => {
  vi.useFakeTimers()
  let requestSignal: AbortSignal | undefined
  const load = (_id: string, signal: AbortSignal) => {
    requestSignal = signal
    return new Promise<JobStatus>(() => {})
  }
  const waiting = waitForJob(client(), job, load, parseGeneratedWord, new AbortController().signal)
  const assertion = expect(waiting).rejects.toMatchObject({ code: 'job_wait_timeout' })
  await vi.advanceTimersByTimeAsync(600_000)
  await assertion
  expect(requestSignal?.aborted).toBe(true)
})
