import { QueryObserver, type QueryClient, type QueryObserverResult } from '@tanstack/react-query'
import { ApiError } from './error'

export type JobReference = { job_id: string; status_url: string }
export type JobStatus = {
  job_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  result: unknown
  error: string | null
  retryAfterSeconds: number
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function parseJobReference(value: unknown): JobReference {
  if (!value || typeof value !== 'object'
    || !('job_id' in value) || typeof value.job_id !== 'string' || !uuid.test(value.job_id)
    || !('status_url' in value) || value.status_url !== `/v1/jobs/${value.job_id}`) {
    throw new ApiError(502, 'invalid_response')
  }
  return { job_id: value.job_id, status_url: value.status_url }
}
export function retryAfter(response?: Response): number {
  const seconds = Number(response?.headers.get('Retry-After'))
  return Number.isFinite(seconds) && seconds > 0 ? seconds : 2
}
export function parseJobStatus(value: unknown, response?: Response): JobStatus {
  if (!value || typeof value !== 'object'
    || !('job_id' in value) || typeof value.job_id !== 'string' || !uuid.test(value.job_id)
    || !('status' in value) || typeof value.status !== 'string'
    || !['queued', 'running', 'succeeded', 'failed'].includes(value.status)
    || !('result' in value) || !('error' in value)
    || (value.error !== null && typeof value.error !== 'string')) {
    throw new ApiError(502, 'invalid_response')
  }
  return {
    job_id: value.job_id, status: value.status as JobStatus['status'],
    result: value.result, error: value.error, retryAfterSeconds: retryAfter(response),
  }
}
export function parseGeneratedWord(value: unknown): number {
  if (!value || typeof value !== 'object' || !('word_id' in value)
    || typeof value.word_id !== 'number' || !Number.isSafeInteger(value.word_id) || value.word_id <= 0) {
    throw new ApiError(502, 'invalid_response')
  }
  return value.word_id
}

export async function waitForJob<T>(
  client: QueryClient,
  job: JobReference,
  load: (id: string, signal: AbortSignal) => Promise<JobStatus>,
  parse: (value: unknown) => T,
  signal: AbortSignal,
): Promise<T> {
  signal.throwIfAborted()
  const started = Date.now()
  const observer = new QueryObserver<JobStatus, Error>(client, {
    queryKey: ['jobs', job.job_id],
    queryFn: async ({ signal }) => {
      const status = await load(job.job_id, signal)
      if (status.job_id !== job.job_id) throw new ApiError(502, 'invalid_response')
      return status
    },
    gcTime: 0,
    retry: (_, error) => !(error instanceof ApiError) || error.status === 503,
    retryDelay: (failures, error) => Math.max(
      error instanceof ApiError ? (error.retryAfterSeconds ?? 2) * 1000 : 0,
      Math.min(30_000, 2000 * 2 ** Math.min(failures, 4)),
    ),
    refetchInterval: query => {
      const status = query.state.data
      if (query.state.error || status?.status === 'succeeded' || status?.status === 'failed') return false
      return Math.max((status?.retryAfterSeconds ?? 2) * 1000, Date.now() - started > 30_000 ? 5000 : 2000)
    },
    refetchIntervalInBackground: false,
  })
  let unsubscribe = () => {}
  let timer: ReturnType<typeof setTimeout> | undefined
  let abort = () => {}
  try {
    const status = await new Promise<JobStatus>((resolve, reject) => {
      const receive = (result: QueryObserverResult<JobStatus, Error>) => {
        if (result.isError) reject(result.error)
        else if (result.data?.status === 'succeeded' || result.data?.status === 'failed') {
          resolve(result.data)
        }
      }
      abort = () => reject(signal.reason)
      signal.addEventListener('abort', abort, { once: true })
      timer = setTimeout(() => reject(new ApiError(408, 'job_wait_timeout')), 600_000)
      unsubscribe = observer.subscribe(receive)
      receive(observer.getCurrentResult())
    })
    if (status.status === 'failed') throw new ApiError(422, status.error ?? 'job_failed')
    return parse(status.result)
  } finally {
    clearTimeout(timer)
    signal.removeEventListener('abort', abort)
    unsubscribe()
  }
}

export async function resumeJob<T>(
  client: QueryClient,
  storageKey: string,
  submit: () => Promise<JobReference>,
  load: (id: string, signal: AbortSignal) => Promise<JobStatus>,
  parse: (value: unknown) => T,
  signal: AbortSignal,
): Promise<T> {
  let job: JobReference | undefined
  try {
    const stored = sessionStorage.getItem(storageKey)
    if (stored) job = parseJobReference(JSON.parse(stored))
  } catch { /* Storage is optional; server ownership remains authoritative. */ }
  if (!job) {
    job = await submit()
    try { sessionStorage.setItem(storageKey, JSON.stringify(job)) } catch { /* Continue polling when storage is unavailable. */ }
  }
  try {
    const result = await waitForJob(client, job, load, parse, signal)
    try { sessionStorage.removeItem(storageKey) } catch { /* Optional resume reference. */ }
    return result
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.code === 'job_failed')) {
      try { sessionStorage.removeItem(storageKey) } catch { /* Optional resume reference. */ }
    }
    throw error
  }
}
