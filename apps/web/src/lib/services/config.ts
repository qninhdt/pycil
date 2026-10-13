export type DataMode = 'mock' | 'live'

export function resolveDataMode(value?: string): DataMode {
  if (!value || value === 'live') return 'live'
  if (value === 'mock') return 'mock'
  throw new Error('NEXT_PUBLIC_DATA_MODE must be "mock" or "live".')
}

export const dataMode = resolveDataMode(process.env.NEXT_PUBLIC_DATA_MODE)

export function getApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_PYCIL_API_URL || process.env.PYCIL_API_URL || 'http://127.0.0.1:8000'
  return `${envUrl.replace(/\/$/, '')}/v1`
}
