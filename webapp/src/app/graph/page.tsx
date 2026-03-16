'use client'

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { GraphToolbar } from './components/GraphToolbar'
import { GraphCanvas } from './components/GraphCanvas'
import { NodeDrawer } from './components/NodeDrawer'
import { AIAssistantDrawer } from './components/AIAssistantDrawer'
import { PageBottomBar } from './components/PageBottomBar'
import { ReconConfirmModal } from './components/ReconConfirmModal'
import { GvmConfirmModal } from './components/GvmConfirmModal'
import { ReconLogsDrawer } from './components/ReconLogsDrawer'
import { ViewTabs, type ViewMode, type TunnelStatus } from './components/ViewTabs'
import { DataTable } from './components/DataTable'
import { ActiveSessions } from './components/ActiveSessions'
import { RoeViewer } from './components/RoeViewer'
import { useGraphData, useDimensions, useNodeSelection, useTableData } from './hooks'
import { exportToExcel } from './utils/exportExcel'
import { useTheme, useSession, useReconStatus, useReconSSE, useGvmStatus, useGvmSSE, useGithubHuntStatus, useGithubHuntSSE, useActiveSessions } from '@/hooks'
import { useProjectById } from '@/hooks/useProjects'
import { useProject } from '@/providers/ProjectProvider'
import { GVM_PHASES, GITHUB_HUNT_PHASES } from '@/lib/recon-types'
import styles from './page.module.css'

export default function GraphPage() {
  const router = useRouter()
  const { projectId, userId, currentProject, setCurrentProject, isLoading: projectLoading } = useProject()

  const [activeView, setActiveView] = useState<ViewMode>('graph')

  // Full project data for RoE viewer (only fetched when RoE tab is active)
  const { data: fullProject } = useProjectById(activeView === 'roe' ? projectId : null)
  const [is3D, setIs3D] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [isAIOpen, setIsAIOpen] = useState(false)
  const [isReconModalOpen, setIsReconModalOpen] = useState(false)
  const [activeLogsDrawer, setActiveLogsDrawer] = useState<'recon' | 'gvm' | 'githubHunt' | null>(null)
  const [hasReconData, setHasReconData] = useState(false)
  const [hasGvmData, setHasGvmData] = useState(false)
  const [hasGithubHuntData, setHasGithubHuntData] = useState(false)
  const [graphStats, setGraphStats] = useState<{ totalNodes: number; nodesByType: Record<string, number> } | null>(null)
  const [gvmStats, setGvmStats] = useState<{ totalGvmNodes: number; nodesByType: Record<string, number> } | null>(null)
  const [isGvmModalOpen, setIsGvmModalOpen] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)

  const { selectedNode, drawerOpen, selectNode, clearSelection } = useNodeSelection()
  const dimensions = useDimensions(contentRef)

  // Close all drawers when project changes
  useEffect(() => {
    setIsAIOpen(false)
    setActiveLogsDrawer(null)
    clearSelection()
  }, [projectId, clearSelection])

  // Track .body position for fixed-position log drawers
  useEffect(() => {
    const body = bodyRef.current
    if (!body) return
    const update = () => {
      const rect = body.getBoundingClientRect()
      document.documentElement.style.setProperty('--drawer-top', `${rect.top}px`)
      document.documentElement.style.setProperty('--drawer-bottom', `${window.innerHeight - rect.bottom}px`)
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(body)
    window.addEventListener('resize', update)
    return () => { ro.disconnect(); window.removeEventListener('resize', update) }
  }, [])
  const { isDark } = useTheme()
  const { sessionId, resetSession, switchSession } = useSession()

  // Agent status polling — lightweight fetch every 5s for toolbar indicators
  const [agentSummary, setAgentSummary] = useState<{
    activeCount: number
    conversations: Array<{
      id: string
      title: string
      currentPhase: string
      iterationCount: number
      agentRunning: boolean
      sessionId: string
    }>
  }>({ activeCount: 0, conversations: [] })

  useEffect(() => {
    if (!projectId || !userId) return
    const fetchStatus = async () => {
      try {
        const res = await fetch(`/api/conversations?projectId=${projectId}&userId=${userId}`)
        if (!res.ok) return
        const convs = await res.json()
        const active = convs.filter((c: any) => c.agentRunning)
        setAgentSummary({ activeCount: active.length, conversations: convs })
      } catch { /* ignore fetch errors */ }
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 5000)
    return () => clearInterval(interval)
  }, [projectId, userId])

  // Tunnel status polling — check every 10s which tunnels are active
  const [tunnelStatus, setTunnelStatus] = useState<TunnelStatus>()

  useEffect(() => {
    const fetchTunnels = async () => {
      try {
        const res = await fetch('/api/agent/tunnel-status')
        if (res.ok) setTunnelStatus(await res.json())
      } catch { /* ignore */ }
    }
    fetchTunnels()
    const interval = setInterval(fetchTunnels, 10000)
    return () => clearInterval(interval)
  }, [])

  // Recon status hook - must be before useGraphData to provide isReconRunning
  const {
    state: reconState,
    isLoading: isReconLoading,
    startRecon,
    stopRecon,
    pauseRecon,
    resumeRecon,
  } = useReconStatus({
    projectId,
    enabled: !!projectId,
  })

  // Check if recon is running to enable auto-refresh of graph data
  const isReconRunning = reconState?.status === 'running' || reconState?.status === 'starting'

  // Check if any agent conversation is active (writes attack chain nodes to graph)
  const isAgentRunning = agentSummary.activeCount > 0

  // Graph data with auto-refresh every 5 seconds while recon or agent is running
  const { data, isLoading, error, refetch: refetchGraph } = useGraphData(projectId, {
    isReconRunning,
    isAgentRunning,
  })

  // Recon logs SSE hook
  const {
    logs: reconLogs,
    currentPhase,
    currentPhaseNumber,
    clearLogs,
  } = useReconSSE({
    projectId,
    enabled: reconState?.status === 'running' || reconState?.status === 'starting' || reconState?.status === 'paused' || reconState?.status === 'stopping',
  })

  // GVM status hook
  const {
    state: gvmState,
    isLoading: isGvmLoading,
    error: gvmError,
    startGvm,
    stopGvm,
    pauseGvm,
    resumeGvm,
  } = useGvmStatus({
    projectId,
    enabled: !!projectId,
  })

  const isGvmRunning = gvmState?.status === 'running' || gvmState?.status === 'starting'

  // GVM logs SSE hook
  const {
    logs: gvmLogs,
    currentPhase: gvmCurrentPhase,
    currentPhaseNumber: gvmCurrentPhaseNumber,
    clearLogs: clearGvmLogs,
  } = useGvmSSE({
    projectId,
    enabled: gvmState?.status === 'running' || gvmState?.status === 'starting' || gvmState?.status === 'paused' || gvmState?.status === 'stopping',
  })

  // GitHub Hunt status hook
  const {
    state: githubHuntState,
    isLoading: isGithubHuntLoading,
    startGithubHunt,
    stopGithubHunt,
    pauseGithubHunt,
    resumeGithubHunt,
  } = useGithubHuntStatus({
    projectId,
    enabled: !!projectId,
  })

  const isGithubHuntRunning = githubHuntState?.status === 'running' || githubHuntState?.status === 'starting'

  // GitHub Hunt logs SSE hook
  const {
    logs: githubHuntLogs,
    currentPhase: githubHuntCurrentPhase,
    currentPhaseNumber: githubHuntCurrentPhaseNumber,
    clearLogs: clearGithubHuntLogs,
  } = useGithubHuntSSE({
    projectId,
    enabled: githubHuntState?.status === 'running' || githubHuntState?.status === 'starting' || githubHuntState?.status === 'paused' || githubHuntState?.status === 'stopping',
  })

  // Active sessions hook — polls kali-sandbox session list
  const activeSessions = useActiveSessions({
    enabled: true,
    fastPoll: activeView === 'sessions',
  })

  // ── Table view state (lifted from DataTable) ──────────────────────────
  const tableRows = useTableData(data)
  const [globalFilter, setGlobalFilter] = useState('')
  const [activeNodeTypes, setActiveNodeTypes] = useState<Set<string>>(new Set())
  const [tableInitialized, setTableInitialized] = useState(false)

  const nodeTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    tableRows.forEach(r => {
      counts[r.node.type] = (counts[r.node.type] || 0) + 1
    })
    return counts
  }, [tableRows])

  const nodeTypes = useMemo(() => Object.keys(nodeTypeCounts).sort(), [nodeTypeCounts])

  useEffect(() => {
    if (nodeTypes.length > 0 && !tableInitialized) {
      setActiveNodeTypes(new Set(nodeTypes))
      setTableInitialized(true)
    } else if (tableInitialized) {
      // Auto-enable newly discovered node types (e.g. attack chain nodes created mid-session)
      setActiveNodeTypes((prev: Set<string>) => {
        const newTypes = nodeTypes.filter((t: string) => !prev.has(t))
        if (newTypes.length === 0) return prev
        const next = new Set(prev)
        newTypes.forEach((t: string) => next.add(t))
        return next
      })
    }
  }, [nodeTypes, tableInitialized])

  const filteredByTypeOnly = useMemo(() => {
    if (activeNodeTypes.size === 0) return []
    return tableRows.filter(r => activeNodeTypes.has(r.node.type))
  }, [tableRows, activeNodeTypes])

  // ── Session (chain) visibility ──────────────────────────────────────
  const CHAIN_NODE_TYPES = useMemo(() => new Set([
    'AttackChain', 'ChainStep', 'ChainDecision', 'ChainFailure', 'ChainFinding',
  ]), [])

  const sessionChainIds = useMemo(() => {
    if (!data) return []
    const ids = new Set<string>()
    for (const node of data.nodes) {
      const chainId = node.properties?.chain_id as string | undefined
      if (chainId && CHAIN_NODE_TYPES.has(node.type)) {
        ids.add(chainId)
      }
    }
    return Array.from(ids).sort()
  }, [data, CHAIN_NODE_TYPES])

  const sessionTitles = useMemo(() => {
    if (!data) return {} as Record<string, string>
    const titles: Record<string, string> = {}
    for (const node of data.nodes) {
      if (node.type === 'AttackChain') {
        const chainId = node.properties?.chain_id as string | undefined
        const title = node.properties?.title as string | undefined
        if (chainId && title) {
          titles[chainId] = title
        }
      }
    }
    return titles
  }, [data])

  const [hiddenSessions, setHiddenSessions] = useState<Set<string>>(new Set())

  // Auto-show newly discovered sessions
  useEffect(() => {
    setHiddenSessions((prev: Set<string>) => {
      const updated = new Set<string>()
      for (const id of prev) {
        if (sessionChainIds.includes(id)) updated.add(id)
      }
      return updated.size !== prev.size ? updated : prev
    })
  }, [sessionChainIds])

  const handleToggleSession = useCallback((chainId: string) => {
    setHiddenSessions((prev: Set<string>) => {
      const next = new Set(prev)
      if (next.has(chainId)) next.delete(chainId)
      else next.add(chainId)
      return next
    })
  }, [])

  const handleShowAllSessions = useCallback(() => {
    setHiddenSessions(new Set())
  }, [])

  const handleHideAllSessions = useCallback(() => {
    setHiddenSessions(new Set(sessionChainIds))
  }, [sessionChainIds])

  // "Hide other chains" / "Show all" toggle for the AI drawer
  const isOtherChainsHidden = useMemo(() => {
    if (hiddenSessions.size === 0) return false
    const otherChains = sessionChainIds.filter((id: string) => id !== sessionId)
    if (otherChains.length === 0) return false
    return otherChains.every((id: string) => hiddenSessions.has(id))
  }, [hiddenSessions, sessionChainIds, sessionId])

  const handleToggleOtherChains = useCallback(() => {
    const otherChains = sessionChainIds.filter((id: string) => id !== sessionId)
    setHiddenSessions((prev: Set<string>) => {
      const allOthersHidden = otherChains.every((id: string) => prev.has(id))
      if (allOthersHidden) {
        return new Set()
      } else {
        return new Set(otherChains)
      }
    })
  }, [sessionChainIds, sessionId])
  // ── End session visibility ────────────────────────────────────────

  // Table rows filtered by type + hidden sessions
  const filteredByType = useMemo(() => {
    if (hiddenSessions.size === 0) return filteredByTypeOnly
    return filteredByTypeOnly.filter((r: { node: { type: string; properties: Record<string, unknown> } }) => {
      if (CHAIN_NODE_TYPES.has(r.node.type)) {
        const chainId = r.node.properties?.chain_id as string | undefined
        if (chainId && hiddenSessions.has(chainId)) return false
      }
      return true
    })
  }, [filteredByTypeOnly, hiddenSessions, CHAIN_NODE_TYPES])

  // Filtered graph data for GraphCanvas (filter nodes by type + hidden sessions, then prune links)
  const filteredGraphData = useMemo(() => {
    if (!data) return undefined
    const allTypesActive = activeNodeTypes.size === nodeTypes.length
    const noSessionsHidden = hiddenSessions.size === 0
    if (allTypesActive && noSessionsHidden) return data // nothing filtered
    const filteredNodes = data.nodes.filter(n => {
      if (!activeNodeTypes.has(n.type)) return false
      // Hide chain nodes belonging to hidden sessions
      if (hiddenSessions.size > 0 && CHAIN_NODE_TYPES.has(n.type)) {
        const chainId = n.properties?.chain_id as string | undefined
        if (chainId && hiddenSessions.has(chainId)) return false
      }
      return true
    })
    const visibleIds = new Set(filteredNodes.map(n => n.id))
    const filteredLinks = data.links.filter(l => {
      const srcId = typeof l.source === 'string' ? l.source : l.source.id
      const tgtId = typeof l.target === 'string' ? l.target : l.target.id
      return visibleIds.has(srcId) && visibleIds.has(tgtId)
    })
    return { ...data, nodes: filteredNodes, links: filteredLinks }
  }, [data, activeNodeTypes, nodeTypes.length, hiddenSessions, CHAIN_NODE_TYPES])

  const textFilteredCount = useMemo(() => {
    if (!globalFilter) return filteredByType.length
    const search = globalFilter.toLowerCase()
    return filteredByType.filter(r =>
      r.node.name?.toLowerCase().includes(search) ||
      r.node.type?.toLowerCase().includes(search)
    ).length
  }, [filteredByType, globalFilter])

  const handleToggleNodeType = useCallback((type: string) => {
    setActiveNodeTypes(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }, [])

  const handleSelectAllTypes = useCallback(() => {
    setActiveNodeTypes(new Set(nodeTypes))
  }, [nodeTypes])

  const handleClearAllTypes = useCallback(() => {
    setActiveNodeTypes(new Set())
  }, [])

  const handleExportExcel = useCallback(() => {
    let rows = filteredByType
    if (globalFilter) {
      const search = globalFilter.toLowerCase()
      rows = rows.filter(r =>
        r.node.name?.toLowerCase().includes(search) ||
        r.node.type?.toLowerCase().includes(search)
      )
    }
    exportToExcel(rows)
  }, [filteredByType, globalFilter])

  // ── End table view state ──────────────────────────────────────────────

  // Check if recon data exists
  const checkReconData = useCallback(async () => {
    if (!projectId) return
    try {
      const response = await fetch(`/api/recon/${projectId}/download`, { method: 'HEAD' })
      setHasReconData(response.ok)
    } catch {
      setHasReconData(false)
    }
  }, [projectId])

  // Calculate graph stats when data changes
  useEffect(() => {
    if (data?.nodes) {
      const nodesByType: Record<string, number> = {}
      data.nodes.forEach(node => {
        const type = node.type || 'Unknown'
        nodesByType[type] = (nodesByType[type] || 0) + 1
      })
      setGraphStats({
        totalNodes: data.nodes.length,
        nodesByType,
      })
    } else {
      setGraphStats(null)
    }
  }, [data])

  // Calculate GVM-specific stats from graph data
  useEffect(() => {
    if (data?.nodes) {
      const gvmTypes: Record<string, number> = {}
      let total = 0
      data.nodes.forEach(node => {
        const isGvmVuln = node.type === 'Vulnerability' && node.properties?.source === 'gvm'
        const isGvmTech = node.type === 'Technology' && (node.properties?.detected_by as string[] | undefined)?.includes('gvm')
        if (isGvmVuln || isGvmTech) {
          const type = node.type || 'Unknown'
          gvmTypes[type] = (gvmTypes[type] || 0) + 1
          total++
        }
      })
      setGvmStats(total > 0 ? { totalGvmNodes: total, nodesByType: gvmTypes } : null)
    } else {
      setGvmStats(null)
    }
  }, [data])

  // Check if GVM data exists
  const checkGvmData = useCallback(async () => {
    if (!projectId) return
    try {
      const response = await fetch(`/api/gvm/${projectId}/download`, { method: 'HEAD' })
      setHasGvmData(response.ok)
    } catch {
      setHasGvmData(false)
    }
  }, [projectId])

  // Check if GitHub Hunt data exists
  const checkGithubHuntData = useCallback(async () => {
    if (!projectId) return
    try {
      const response = await fetch(`/api/github-hunt/${projectId}/download`, { method: 'HEAD' })
      setHasGithubHuntData(response.ok)
    } catch {
      setHasGithubHuntData(false)
    }
  }, [projectId])

  // Check for recon/GVM/GitHub Hunt data on mount and when project changes
  useEffect(() => {
    checkReconData()
    checkGvmData()
    checkGithubHuntData()
  }, [checkReconData, checkGvmData, checkGithubHuntData])

  // Refresh graph data when recon completes
  useEffect(() => {
    if (reconState?.status === 'completed' || reconState?.status === 'error') {
      refetchGraph()
      checkReconData()
    }
  }, [reconState?.status, refetchGraph, checkReconData])

  // Refresh graph when GVM scan completes
  useEffect(() => {
    if (gvmState?.status === 'completed' || gvmState?.status === 'error') {
      refetchGraph()
      checkGvmData()
    }
  }, [gvmState?.status, refetchGraph, checkGvmData])

  // Refresh when GitHub Hunt completes
  useEffect(() => {
    if (githubHuntState?.status === 'completed' || githubHuntState?.status === 'error') {
      refetchGraph()
      checkGithubHuntData()
    }
  }, [githubHuntState?.status, refetchGraph, checkGithubHuntData])

  const handleToggleAI = useCallback(() => {
    setIsAIOpen((prev) => !prev)
  }, [])

  const handleCloseAI = useCallback(() => {
    setIsAIOpen(false)
  }, [])

  const handleToggleStealth = useCallback(async (newValue: boolean) => {
    if (!projectId) return
    try {
      const res = await fetch(`/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stealthMode: newValue }),
      })
      if (res.ok && currentProject) {
        setCurrentProject({ ...currentProject, stealthMode: newValue })
      }
    } catch (error) {
      console.error('Failed to toggle stealth mode:', error)
    }
  }, [projectId, currentProject, setCurrentProject])

  const handleToggleDeepThink = useCallback(async (newValue: boolean) => {
    if (!projectId) return
    try {
      const res = await fetch(`/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agentDeepThinkEnabled: newValue }),
      })
      if (res.ok && currentProject) {
        setCurrentProject({ ...currentProject, agentDeepThinkEnabled: newValue })
      }
    } catch (error) {
      console.error('Failed to toggle deep think:', error)
    }
  }, [projectId, currentProject, setCurrentProject])

  const handleModelChange = useCallback(async (modelId: string) => {
    if (!projectId) return
    try {
      const res = await fetch(`/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agentOpenaiModel: modelId }),
      })
      if (res.ok && currentProject) {
        setCurrentProject({ ...currentProject, agentOpenaiModel: modelId })
      }
    } catch (error) {
      console.error('Failed to change model:', error)
    }
  }, [projectId, currentProject, setCurrentProject])

  const handleStartRecon = useCallback(() => {
    setIsReconModalOpen(true)
  }, [])

  const handleConfirmRecon = useCallback(async () => {
    clearLogs()
    const result = await startRecon()
    if (result) {
      setIsReconModalOpen(false)
      setActiveLogsDrawer('recon')
    }
  }, [startRecon, clearLogs])

  const handleDownloadJSON = useCallback(async () => {
    if (!projectId) return
    window.open(`/api/recon/${projectId}/download`, '_blank')
  }, [projectId])

  const handleDeleteNode = useCallback(async (nodeId: string) => {
    if (!projectId) return
    const res = await fetch(`/api/graph?nodeId=${nodeId}&projectId=${projectId}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const data = await res.json()
      alert(data.error || 'Failed to delete node')
      return
    }
    refetchGraph()
  }, [projectId, refetchGraph])

  const handleToggleLogs = useCallback(() => {
    setActiveLogsDrawer(prev => prev === 'recon' ? null : 'recon')
  }, [])

  const handleStartGvm = useCallback(() => {
    setIsGvmModalOpen(true)
  }, [])

  const handleConfirmGvm = useCallback(async () => {
    clearGvmLogs()
    const result = await startGvm()
    if (result) {
      setIsGvmModalOpen(false)
      setActiveLogsDrawer('gvm')
    }
  }, [startGvm, clearGvmLogs])

  const handleDownloadGvmJSON = useCallback(async () => {
    if (!projectId) return
    window.open(`/api/gvm/${projectId}/download`, '_blank')
  }, [projectId])

  const handleToggleGvmLogs = useCallback(() => {
    setActiveLogsDrawer(prev => prev === 'gvm' ? null : 'gvm')
  }, [])

  const handleStartGithubHunt = useCallback(async () => {
    clearGithubHuntLogs()
    const result = await startGithubHunt()
    if (result) {
      setActiveLogsDrawer('githubHunt')
    }
  }, [startGithubHunt, clearGithubHuntLogs])

  const handleDownloadGithubHuntJSON = useCallback(async () => {
    if (!projectId) return
    window.open(`/api/github-hunt/${projectId}/download`, '_blank')
  }, [projectId])

  const handleToggleGithubHuntLogs = useCallback(() => {
    setActiveLogsDrawer(prev => prev === 'githubHunt' ? null : 'githubHunt')
  }, [])

  // Pause/Resume/Stop handlers
  const handlePauseRecon = useCallback(async () => { await pauseRecon() }, [pauseRecon])
  const handleResumeRecon = useCallback(async () => { await resumeRecon() }, [resumeRecon])
  const handleStopRecon = useCallback(async () => { await stopRecon() }, [stopRecon])
  const handlePauseGvm = useCallback(async () => { await pauseGvm() }, [pauseGvm])
  const handleResumeGvm = useCallback(async () => { await resumeGvm() }, [resumeGvm])
  const handleStopGvm = useCallback(async () => { await stopGvm() }, [stopGvm])
  const handlePauseGithubHunt = useCallback(async () => { await pauseGithubHunt() }, [pauseGithubHunt])
  const handleResumeGithubHunt = useCallback(async () => { await resumeGithubHunt() }, [resumeGithubHunt])
  const handleStopGithubHunt = useCallback(async () => { await stopGithubHunt() }, [stopGithubHunt])

  // Emergency Pause All — freezes every running pipeline and agent at once
  const isAnyPipelineRunning = isReconRunning || isGvmRunning || isGithubHuntRunning || isAgentRunning
  const [isEmergencyPausing, setIsEmergencyPausing] = useState(false)

  // Auto-clear the pausing state once all pipelines have actually stopped
  useEffect(() => {
    if (isEmergencyPausing && !isAnyPipelineRunning) {
      setIsEmergencyPausing(false)
    }
  }, [isEmergencyPausing, isAnyPipelineRunning])

  const handleEmergencyPauseAll = useCallback(async () => {
    setIsEmergencyPausing(true)
    const tasks: Promise<unknown>[] = []
    if (reconState?.status === 'running' || reconState?.status === 'starting') {
      tasks.push(pauseRecon())
    }
    if (gvmState?.status === 'running' || gvmState?.status === 'starting') {
      tasks.push(pauseGvm())
    }
    if (githubHuntState?.status === 'running' || githubHuntState?.status === 'starting') {
      tasks.push(pauseGithubHunt())
    }
    // Stop all running AI agent conversations
    tasks.push(fetch('/api/agent/emergency-stop-all', { method: 'POST' }))
    await Promise.allSettled(tasks)
  }, [reconState?.status, gvmState?.status, githubHuntState?.status, pauseRecon, pauseGvm, pauseGithubHunt])

  // Show message if no project is selected
  if (!projectLoading && !projectId) {
    return (
      <div className={styles.page}>
        <div className={styles.noProject}>
          <h2>No Project Selected</h2>
          <p>Select a project from the dropdown in the header or create a new one.</p>
          <button className="primaryButton" onClick={() => router.push('/projects')}>
            Go to Projects
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <GraphToolbar
        projectId={projectId || ''}
        is3D={is3D}
        showLabels={showLabels}
        onToggle3D={setIs3D}
        onToggleLabels={setShowLabels}
        onToggleAI={handleToggleAI}
        isAIOpen={isAIOpen}
        // Target info
        targetDomain={currentProject?.targetDomain}
        subdomainList={currentProject?.subdomainList}
        // Recon props
        onStartRecon={handleStartRecon}
        onPauseRecon={handlePauseRecon}
        onResumeRecon={handleResumeRecon}
        onStopRecon={handleStopRecon}
        onDownloadJSON={handleDownloadJSON}
        onToggleLogs={handleToggleLogs}
        reconStatus={reconState?.status || 'idle'}
        hasReconData={hasReconData}
        isLogsOpen={activeLogsDrawer === 'recon'}
        // GVM props
        onStartGvm={handleStartGvm}
        onPauseGvm={handlePauseGvm}
        onResumeGvm={handleResumeGvm}
        onStopGvm={handleStopGvm}
        onDownloadGvmJSON={handleDownloadGvmJSON}
        onToggleGvmLogs={handleToggleGvmLogs}
        gvmStatus={gvmState?.status || 'idle'}
        hasGvmData={hasGvmData}
        isGvmLogsOpen={activeLogsDrawer === 'gvm'}
        // GitHub Hunt props
        onStartGithubHunt={handleStartGithubHunt}
        onPauseGithubHunt={handlePauseGithubHunt}
        onResumeGithubHunt={handleResumeGithubHunt}
        onStopGithubHunt={handleStopGithubHunt}
        onDownloadGithubHuntJSON={handleDownloadGithubHuntJSON}
        onToggleGithubHuntLogs={handleToggleGithubHuntLogs}
        githubHuntStatus={githubHuntState?.status || 'idle'}
        hasGithubHuntData={hasGithubHuntData}
        isGithubHuntLogsOpen={activeLogsDrawer === 'githubHunt'}
        // Stealth mode
        stealthMode={currentProject?.stealthMode}
        // RoE
        roeEnabled={currentProject?.roeEnabled}
        // Emergency Pause All
        onEmergencyPauseAll={handleEmergencyPauseAll}
        isAnyPipelineRunning={isAnyPipelineRunning}
        isEmergencyPausing={isEmergencyPausing}
        // Agent status
        agentActiveCount={agentSummary.activeCount}
        agentConversations={agentSummary.conversations}
      />

      <ViewTabs
        activeView={activeView}
        onViewChange={setActiveView}
        globalFilter={globalFilter}
        onGlobalFilterChange={setGlobalFilter}
        onExport={handleExportExcel}
        totalRows={filteredByType.length}
        filteredRows={textFilteredCount}
        sessionCount={activeSessions.totalCount}
        tunnelStatus={tunnelStatus}
      />

      <div ref={bodyRef} className={styles.body}>
        {activeView === 'graph' && (
          <NodeDrawer
            node={selectedNode}
            isOpen={drawerOpen}
            onClose={clearSelection}
            onDeleteNode={handleDeleteNode}
          />
        )}

        <div ref={contentRef} className={styles.content}>
          {activeView === 'graph' ? (
            <GraphCanvas
              data={filteredGraphData}
              isLoading={isLoading}
              error={error}
              projectId={projectId || ''}
              is3D={is3D}
              width={dimensions.width}
              height={dimensions.height}
              showLabels={showLabels}
              selectedNode={selectedNode}
              onNodeClick={selectNode}
              isDark={isDark}
              activeChainId={sessionId}
            />
          ) : activeView === 'table' ? (
            <DataTable
              data={data}
              isLoading={isLoading}
              error={error}
              rows={filteredByType}
              globalFilter={globalFilter}
              onGlobalFilterChange={setGlobalFilter}
            />
          ) : activeView === 'sessions' ? (
            <ActiveSessions
              sessions={activeSessions.sessions}
              jobs={activeSessions.jobs}
              nonMsfSessions={activeSessions.nonMsfSessions}
              agentBusy={activeSessions.agentBusy}
              isLoading={activeSessions.isLoading}
              projectId={projectId || ''}
              onInteract={activeSessions.interactWithSession}
              onKillSession={activeSessions.killSession}
              onKillJob={activeSessions.killJob}
            />
          ) : activeView === 'roe' ? (
            <RoeViewer
              projectId={projectId || ''}
              project={fullProject || {}}
            />
          ) : null}
        </div>

      </div>

      <ReconLogsDrawer
        isOpen={activeLogsDrawer === 'recon'}
        onClose={() => setActiveLogsDrawer(null)}
        logs={reconLogs}
        currentPhase={currentPhase}
        currentPhaseNumber={currentPhaseNumber}
        status={reconState?.status || 'idle'}
        onClearLogs={clearLogs}
        onPause={handlePauseRecon}
        onResume={handleResumeRecon}
        onStop={handleStopRecon}
      />

      <ReconLogsDrawer
        isOpen={activeLogsDrawer === 'gvm'}
        onClose={() => setActiveLogsDrawer(null)}
        logs={gvmLogs}
        currentPhase={gvmCurrentPhase}
        currentPhaseNumber={gvmCurrentPhaseNumber}
        status={gvmState?.status || 'idle'}
        onClearLogs={clearGvmLogs}
        onPause={handlePauseGvm}
        onResume={handleResumeGvm}
        onStop={handleStopGvm}
        title="GVM Vulnerability Scan Logs"
        phases={GVM_PHASES}
        totalPhases={4}
      />

      <ReconLogsDrawer
        isOpen={activeLogsDrawer === 'githubHunt'}
        onClose={() => setActiveLogsDrawer(null)}
        logs={githubHuntLogs}
        currentPhase={githubHuntCurrentPhase}
        currentPhaseNumber={githubHuntCurrentPhaseNumber}
        status={githubHuntState?.status || 'idle'}
        onClearLogs={clearGithubHuntLogs}
        onPause={handlePauseGithubHunt}
        onResume={handleResumeGithubHunt}
        onStop={handleStopGithubHunt}
        title="GitHub Secret Hunt Logs"
        phases={GITHUB_HUNT_PHASES}
        totalPhases={3}
      />

      <AIAssistantDrawer
        isOpen={isAIOpen}
        onClose={handleCloseAI}
        userId={userId || ''}
        projectId={projectId || ''}
        sessionId={sessionId || ''}
        onResetSession={resetSession}
        onSwitchSession={switchSession}
        modelName={currentProject?.agentOpenaiModel}
        onModelChange={handleModelChange}
        toolPhaseMap={currentProject?.agentToolPhaseMap}
        stealthMode={currentProject?.stealthMode}
        onToggleStealth={handleToggleStealth}
        deepThinkEnabled={currentProject?.agentDeepThinkEnabled}
        onToggleDeepThink={handleToggleDeepThink}
        onRefetchGraph={refetchGraph}
        isOtherChainsHidden={isOtherChainsHidden}
        onToggleOtherChains={handleToggleOtherChains}
        hasOtherChains={sessionChainIds.length > 1 || (sessionChainIds.length === 1 && sessionChainIds[0] !== sessionId)}
      />

      <ReconConfirmModal
        isOpen={isReconModalOpen}
        onClose={() => setIsReconModalOpen(false)}
        onConfirm={handleConfirmRecon}
        projectName={currentProject?.name || 'Unknown'}
        targetDomain={currentProject?.targetDomain || 'Unknown'}
        ipMode={currentProject?.ipMode}
        targetIps={currentProject?.targetIps}
        stats={graphStats}
        isLoading={isReconLoading}
      />

      <GvmConfirmModal
        isOpen={isGvmModalOpen}
        onClose={() => setIsGvmModalOpen(false)}
        onConfirm={handleConfirmGvm}
        projectName={currentProject?.name || 'Unknown'}
        targetDomain={currentProject?.targetDomain || currentProject?.targetIps?.join(', ') || 'Unknown'}
        stats={gvmStats}
        isLoading={isGvmLoading}
        error={gvmError}
      />

      <PageBottomBar
        data={data}
        is3D={is3D}
        showLabels={showLabels}
        activeView={activeView}
        activeNodeTypes={activeNodeTypes}
        nodeTypeCounts={nodeTypeCounts}
        onToggleNodeType={handleToggleNodeType}
        onSelectAllTypes={handleSelectAllTypes}
        onClearAllTypes={handleClearAllTypes}
        sessionChainIds={sessionChainIds}
        sessionTitles={sessionTitles}
        hiddenSessions={hiddenSessions}
        onToggleSession={handleToggleSession}
        onShowAllSessions={handleShowAllSessions}
        onHideAllSessions={handleHideAllSessions}
      />
    </div>
  )
}
