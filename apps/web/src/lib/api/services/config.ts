import { localApiOrigin } from '../../../config'
export type DataMode = 'mock' | 'live'

export function resolveDataMode(value?: string): DataMode {
  if (!value || value === 'live') return 'live'
  if (value === 'mock') return 'mock'
  throw new Error('NEXT_PUBLIC_DATA_MODE must be "mock" or "live".')
}

export const dataMode = resolveDataMode(process.env.NEXT_PUBLIC_DATA_MODE)

export function getApiBaseUrl(): string {
  const envUrl = (typeof window === 'undefined' ? process.env.PYCIL_API_URL || process.env.NEXT_PUBLIC_PYCIL_API_URL : process.env.NEXT_PUBLIC_PYCIL_API_URL) || localApiOrigin
  return `${envUrl.replace(/\/$/, '')}/v1`
}
