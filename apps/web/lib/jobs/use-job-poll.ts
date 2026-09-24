"use client"

import { useEffect, useState } from "react"

import { createApiClient } from "@/lib/api/client"
import type { JobSnapshot } from "@/lib/api/resources/jobs"

const DELAYS = [600, 1200, 2400, 4000]

export function useJobPoll(jobId: string | null): JobSnapshot | null {
  const [held, setHeld] = useState<{ jobId: string | null; snapshot: JobSnapshot | null }>({
    jobId: null,
    snapshot: null,
  })

  useEffect(() => {
    if (!jobId) {
      return
    }
    let active = true
    let attempt = 0
    const client = createApiClient()
    let timer: ReturnType<typeof setTimeout> | undefined

    const poll = async () => {
      try {
        const next = await client.jobs.get(jobId)
        if (!active) return
        setHeld({ jobId, snapshot: next })
        if (next.status === "queued" || next.status === "running") {
          timer = setTimeout(poll, DELAYS[Math.min(attempt++, DELAYS.length - 1)])
        }
      } catch {
        if (active) timer = setTimeout(poll, DELAYS[Math.min(attempt++, DELAYS.length - 1)])
      }
    }

    void poll()
    return () => {
      active = false
      if (timer) clearTimeout(timer)
    }
  }, [jobId])

  return held.jobId === jobId ? held.snapshot : null
}
