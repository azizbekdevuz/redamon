'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import type { MsfSession, MsfJob, NonMsfSession, SessionInteractResult } from '@/lib/websocket-types'

interface UseActiveSessionsOptions {
  enabled?: boolean
  fastPoll?: boolean // 3s when true, 10s when false
}

interface UseActiveSessionsReturn {
  sessions: MsfSession[]
  jobs: MsfJob[]
  nonMsfSessions: NonMsfSession[]
  agentBusy: boolean
  isLoading: boolean
  error: string | null
  totalCount: number
  interactWithSession: (sessionId: number, command: string) => Promise<SessionInteractResult>
  killSession: (sessionId: number) => Promise<void>
  killJob: (jobId: number) => Promise<void>
  refetch: () => Promise<void>
}

const FAST_INTERVAL = 3000
const SLOW_INTERVAL = 10000

export function useActiveSessions({
  enabled = true,
  fastPoll = false,
}: UseActiveSessionsOptions = {}): UseActiveSessionsReturn {
  const [sessions, setSessions] = useState<MsfSession[]>([])
  const [jobs, setJobs] = useState<MsfJob[]>([])
  const [nonMsfSessions, setNonMsfSessions] = useState<NonMsfSession[]>([])
  const [agentBusy, setAgentBusy] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)
  // Track killed sessions/jobs so polls don't re-add them
  const killedSessionsRef = useRef<Set<number>>(new Set())
  const killedJobsRef = useRef<Set<number>>(new Set())

  const fetchSessions = useCallback(async () => {
    try {
      const resp = await fetch('/api/agent/sessions', { cache: 'no-store' })
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }
      const data = await resp.json()
      const liveSessions: MsfSession[] = data.sessions || []
      const liveJobs: MsfJob[] = data.jobs || []
      // Clear killed IDs that are truly gone from the server
      for (const sid of killedSessionsRef.current) {
        if (!liveSessions.some(s => s.id === sid)) killedSessionsRef.current.delete(sid)
      }
      for (const jid of killedJobsRef.current) {
        if (!liveJobs.some(j => j.id === jid)) killedJobsRef.current.delete(jid)
      }
      // Filter out sessions/jobs that are pending kill
      setSessions(liveSessions.filter(s => !killedSessionsRef.current.has(s.id)))
      setJobs(liveJobs.filter(j => !killedJobsRef.current.has(j.id)))
      setNonMsfSessions(data.non_msf_sessions || [])
      setAgentBusy(data.agent_busy || false)
      setError(null)
    } catch (err) {
      // Don't clear sessions on transient errors — keep showing last known state
      setError(err instanceof Error ? err.message : 'Failed to fetch sessions')
    }
  }, [])

  const interactWithSession = useCallback(async (sessionId: number, command: string): Promise<SessionInteractResult> => {
    try {
      const resp = await fetch(`/api/agent/sessions/${sessionId}/interact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      })
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }
      return await resp.json()
    } catch (err) {
      return { busy: false, output: `[ERROR] ${err instanceof Error ? err.message : 'Unknown error'}` }
    }
  }, [])

  const killSession = useCallback(async (sessionId: number) => {
    // Mark as killed immediately so polls don't re-add it
    killedSessionsRef.current.add(sessionId)
    setSessions(prev => prev.filter(s => s.id !== sessionId))
    try {
      await fetch(`/api/agent/sessions/${sessionId}/kill`, { method: 'POST' })
    } catch {
      // Optimistic removal stays — will self-correct if session is still alive
      killedSessionsRef.current.delete(sessionId)
    }
  }, [])

  const killJob = useCallback(async (jobId: number) => {
    // Mark as killed immediately so polls don't re-add it
    killedJobsRef.current.add(jobId)
    setJobs(prev => prev.filter(j => j.id !== jobId))
    try {
      await fetch(`/api/agent/jobs/${jobId}/kill`, { method: 'POST' })
    } catch {
      // Optimistic removal stays — will self-correct if job is still alive
      killedJobsRef.current.delete(jobId)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    if (!enabled) return
    setIsLoading(true)
    fetchSessions().finally(() => setIsLoading(false))
  }, [enabled, fetchSessions])

  // Smart polling
  useEffect(() => {
    if (!enabled) return

    if (pollingRef.current) {
      clearInterval(pollingRef.current)
    }

    const interval = fastPoll ? FAST_INTERVAL : SLOW_INTERVAL
    pollingRef.current = setInterval(fetchSessions, interval)

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
  }, [enabled, fastPoll, fetchSessions])

  const totalCount = sessions.length + nonMsfSessions.length

  return {
    sessions,
    jobs,
    nonMsfSessions,
    agentBusy,
    isLoading,
    error,
    totalCount,
    interactWithSession,
    killSession,
    killJob,
    refetch: fetchSessions,
  }
}

export default useActiveSessions
