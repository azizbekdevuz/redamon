/**
 * AI Assistant Drawer - WebSocket Version
 *
 * Real-time bidirectional communication with the agent using WebSocket.
 * Features streaming thoughts, tool executions, and beautiful timeline UI.
 * Single scrollable chat with all messages, thinking, and tool executions inline.
 */

'use client'

import React, { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react'
import { Send, Bot, User, Loader2, AlertCircle, Sparkles, Plus, Shield, ShieldAlert, Target, Zap, HelpCircle, WifiOff, Wifi, Square, Play, Download, Wrench, History, ChevronDown, EyeOff, Eye, Mail, Copy, Check } from 'lucide-react'
import { StealthIcon } from '@/components/icons/StealthIcon'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import styles from './AIAssistantDrawer.module.css'
import { useAgentWebSocket } from '@/hooks/useAgentWebSocket'
import {
  MessageType,
  ConnectionStatus,
  type ServerMessage,
  type ApprovalRequestPayload,
  type QuestionRequestPayload,
  type TodoItem
} from '@/lib/websocket-types'
import { AgentTimeline } from './AgentTimeline'
import { FileDownloadCard } from './FileDownloadCard'
import { TodoListWidget } from './TodoListWidget'
import { ConversationHistory } from './ConversationHistory'
import { useConversations } from '@/hooks/useConversations'
import { useChatPersistence } from '@/hooks/useChatPersistence'
import type { Conversation } from '@/hooks/useConversations'
import { Tooltip } from '@/components/ui/Tooltip/Tooltip'
import type { ThinkingItem, ToolExecutionItem } from './AgentTimeline'

type Phase = 'informational' | 'exploitation' | 'post_exploitation'

/** Recursively extract plain text from React children (for copy-to-clipboard). */
function extractTextFromChildren(children: any): string {
  if (children == null) return ''
  if (typeof children === 'string') return children
  if (typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(extractTextFromChildren).join('')
  if (children?.props?.children) return extractTextFromChildren(children.props.children)
  return ''
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolUsed?: string | null
  toolOutput?: string | null
  error?: string | null
  phase?: Phase
  timestamp: Date
  isGuidance?: boolean
  isReport?: boolean
  responseTier?: 'conversational' | 'summary' | 'full_report'
}

interface FileDownloadItem {
  type: 'file_download'
  id: string
  timestamp: Date
  filepath: string
  filename: string
  description: string
  source: string
}

type ChatItem = Message | ThinkingItem | ToolExecutionItem | FileDownloadItem

/** Format prefixed model names for display (e.g. "openrouter/meta-llama/llama-4" → "llama-4 (OR)") */
function formatModelDisplay(model: string): string {
  if (model.startsWith('openai_compat/')) {
    const parts = model.slice('openai_compat/'.length).split('/')
    return `${parts[parts.length - 1]} (OA-Compat)`
  }
  if (model.startsWith('openrouter/')) {
    const parts = model.slice('openrouter/'.length).split('/')
    return `${parts[parts.length - 1]} (OR)`
  }
  if (model.startsWith('bedrock/')) {
    const simplified = model.slice('bedrock/'.length).replace(/^[^.]+\./, '').replace(/-\d{8}-v\d+:\d+$/, '')
    return `${simplified} (Bedrock)`
  }
  return model
}

interface AIAssistantDrawerProps {
  isOpen: boolean
  onClose: () => void
  userId: string
  projectId: string
  sessionId: string
  onResetSession?: () => string
  onSwitchSession?: (sessionId: string) => void
  modelName?: string
  toolPhaseMap?: Record<string, string[]>
  stealthMode?: boolean
  onToggleStealth?: (newValue: boolean) => void
  onRefetchGraph?: () => void
  isOtherChainsHidden?: boolean
  onToggleOtherChains?: () => void
  hasOtherChains?: boolean
}

const PHASE_CONFIG = {
  informational: {
    label: 'Informational',
    icon: Shield,
    color: '#059669',
    bgColor: 'rgba(5, 150, 105, 0.1)',
  },
  exploitation: {
    label: 'Exploitation',
    icon: Target,
    color: 'var(--status-warning)',
    bgColor: 'rgba(245, 158, 11, 0.1)',
  },
  post_exploitation: {
    label: 'Post-Exploitation',
    icon: Zap,
    color: 'var(--status-error)',
    bgColor: 'rgba(239, 68, 68, 0.1)',
  },
}

const KNOWN_ATTACK_PATH_CONFIG: Record<string, { label: string; shortLabel: string; color: string; bgColor: string }> = {
  cve_exploit: {
    label: 'CVE Exploit',
    shortLabel: 'CVE',
    color: 'var(--status-warning)',
    bgColor: 'rgba(245, 158, 11, 0.15)',
  },
  brute_force_credential_guess: {
    label: 'Brute Force',
    shortLabel: 'BRUTE',
    color: 'var(--accent-secondary, #8b5cf6)',
    bgColor: 'rgba(139, 92, 246, 0.15)',
  },
  phishing_social_engineering: {
    label: 'Phishing / Social Engineering',
    shortLabel: 'PHISH',
    color: 'var(--accent-tertiary, #ec4899)',
    bgColor: 'rgba(236, 72, 153, 0.15)',
  },
}

/** Derive display config for any attack path type (known or unclassified). */
function getAttackPathConfig(type: string): { label: string; shortLabel: string; color: string; bgColor: string } {
  if (KNOWN_ATTACK_PATH_CONFIG[type]) {
    return KNOWN_ATTACK_PATH_CONFIG[type]
  }
  // Unclassified: derive label from the type string
  // e.g. "sql_injection-unclassified" -> label "Sql Injection", shortLabel "SI"
  const cleanName = type.replace(/-unclassified$/, '').replace(/_/g, ' ')
  const words = cleanName.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1))
  const label = words.join(' ')
  const shortLabel = words.length === 1
    ? label.slice(0, 5).toUpperCase()
    : words.map(w => w[0]).join('').toUpperCase()
  return {
    label: `${label} (Unclassified)`,
    shortLabel,
    color: 'var(--text-secondary, #6b7280)',
    bgColor: 'rgba(107, 114, 128, 0.15)',
  }
}

export function AIAssistantDrawer({
  isOpen,
  onClose,
  userId,
  projectId,
  sessionId,
  onResetSession,
  onSwitchSession,
  modelName,
  toolPhaseMap,
  stealthMode = false,
  onToggleStealth,
  onRefetchGraph,
  isOtherChainsHidden = false,
  onToggleOtherChains,
  hasOtherChains = false,
}: AIAssistantDrawerProps) {
  const [chatItems, setChatItems] = useState<ChatItem[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isStopped, setIsStopped] = useState(false)
  const [currentPhase, setCurrentPhase] = useState<Phase>('informational')
  const [attackPathType, setAttackPathType] = useState<string>('cve_exploit')
  const [iterationCount, setIterationCount] = useState(0)
  const [awaitingApproval, setAwaitingApproval] = useState(false)
  const [approvalRequest, setApprovalRequest] = useState<ApprovalRequestPayload | null>(null)
  const [modificationText, setModificationText] = useState('')

  // Q&A state
  const [awaitingQuestion, setAwaitingQuestion] = useState(false)
  const [questionRequest, setQuestionRequest] = useState<QuestionRequestPayload | null>(null)
  const [answerText, setAnswerText] = useState('')
  const [selectedOptions, setSelectedOptions] = useState<string[]>([])

  const [todoList, setTodoList] = useState<TodoItem[]>([])
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const [copiedFieldKey, setCopiedFieldKey] = useState<string | null>(null)

  // Conversation history state
  const [showHistory, setShowHistory] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)

  // Template dropdown state
  const [openTemplateGroup, setOpenTemplateGroup] = useState<string | null>(null)

  // Conversation hooks
  const {
    conversations,
    fetchConversations,
    createConversation,
    deleteConversation,
    loadConversation,
  } = useConversations(projectId, userId)

  const { saveMessage, updateConversation: updateConvMeta } = useChatPersistence(conversationId)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const isProcessingApproval = useRef(false)
  const awaitingApprovalRef = useRef(false)
  const isProcessingQuestion = useRef(false)
  const awaitingQuestionRef = useRef(false)
  const shouldAutoScroll = useRef(true)
  const itemIdCounter = useRef(0)

  const scrollToBottom = useCallback((force = false) => {
    if (force || shouldAutoScroll.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  // Check if user is at the bottom of the scroll
  const checkIfAtBottom = useCallback(() => {
    const container = messagesContainerRef.current
    if (!container) return true

    const threshold = 50 // pixels from bottom
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < threshold

    shouldAutoScroll.current = isAtBottom
    return isAtBottom
  }, [])

  // Auto-scroll only if user is at bottom
  useEffect(() => {
    scrollToBottom()
  }, [chatItems, scrollToBottom])

  useEffect(() => {
    if (isOpen && inputRef.current && !awaitingApproval) {
      setTimeout(() => {
        inputRef.current?.focus()
        scrollToBottom(true) // Force scroll to bottom when opening
      }, 300)
    }
  }, [isOpen, awaitingApproval, scrollToBottom])

  // Fetch conversations when history panel opens, auto-refresh every 5s
  useEffect(() => {
    if (showHistory && projectId && userId) {
      fetchConversations()
      const interval = setInterval(fetchConversations, 5000)
      return () => clearInterval(interval)
    }
  }, [showHistory, projectId, userId, fetchConversations])

  // Reset state when session changes (skip if switching to a loaded conversation)
  const isRestoringConversation = useRef(false)
  useEffect(() => {
    if (isRestoringConversation.current) {
      isRestoringConversation.current = false
      return
    }
    setChatItems([])
    setCurrentPhase('informational')
    setAttackPathType('cve_exploit')
    setIterationCount(0)
    setAwaitingApproval(false)
    setApprovalRequest(null)
    setAwaitingQuestion(false)
    setQuestionRequest(null)
    setAnswerText('')
    setSelectedOptions([])
    setTodoList([])
    setIsStopped(false)
    setIsLoading(false)
    awaitingApprovalRef.current = false
    isProcessingApproval.current = false
    awaitingQuestionRef.current = false
    isProcessingQuestion.current = false
    shouldAutoScroll.current = true // Reset to auto-scroll on new session
  }, [sessionId])

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((message: ServerMessage) => {
    switch (message.type) {
      case MessageType.CONNECTED:
        break

      case MessageType.THINKING:
        // Add thinking item to chat
        const thinkingItem: ThinkingItem = {
          type: 'thinking',
          id: `thinking-${Date.now()}-${itemIdCounter.current++}`,
          timestamp: new Date(),
          thought: message.payload.thought || '',
          reasoning: message.payload.reasoning || '',
          action: 'thinking',
          updated_todo_list: todoList,
        }
        setChatItems(prev => [...prev, thinkingItem])
        setIsLoading(true)
        setIsStopped(false)
        break

      case MessageType.TOOL_START:
        // Add tool execution item to chat
        const toolItem: ToolExecutionItem = {
          type: 'tool_execution',
          id: `tool-${Date.now()}-${itemIdCounter.current++}`,
          timestamp: new Date(),
          tool_name: message.payload.tool_name,
          tool_args: message.payload.tool_args,
          status: 'running',
          output_chunks: [],
        }
        setChatItems(prev => [...prev, toolItem])
        setIsLoading(true)
        break

      case MessageType.TOOL_OUTPUT_CHUNK:
        // Append output chunk to the matching tool execution item (by tool_name)
        setChatItems(prev => {
          // Find the tool execution item by tool_name (handles any ordering)
          const toolIndex = prev.findIndex(
            item => 'type' in item &&
                    item.type === 'tool_execution' &&
                    item.tool_name === message.payload.tool_name &&
                    item.status === 'running'
          )
          if (toolIndex !== -1) {
            const toolItem = prev[toolIndex] as ToolExecutionItem
            return [
              ...prev.slice(0, toolIndex),
              {
                ...toolItem,
                output_chunks: [...toolItem.output_chunks, message.payload.chunk],
              },
              ...prev.slice(toolIndex + 1)
            ]
          }
          return prev
        })
        break

      case MessageType.TOOL_COMPLETE:
        // Mark tool as complete and add rich analysis data
        setChatItems(prev => {
          // Find the tool execution item (may not be the last item due to message ordering)
          const toolIndex = prev.findIndex(
            item => 'type' in item &&
                    item.type === 'tool_execution' &&
                    item.tool_name === message.payload.tool_name &&
                    item.status === 'running'
          )
          if (toolIndex !== -1) {
            const toolItem = prev[toolIndex] as ToolExecutionItem
            const updatedItem: ToolExecutionItem = {
              ...toolItem,
              status: message.payload.success ? 'success' : 'error',
              final_output: message.payload.output_summary,
              actionable_findings: message.payload.actionable_findings || [],
              recommended_next_steps: message.payload.recommended_next_steps || [],
            }
            return [
              ...prev.slice(0, toolIndex),
              updatedItem,
              ...prev.slice(toolIndex + 1)
            ]
          }
          return prev
        })
        setIsLoading(false)
        break

      case MessageType.PHASE_UPDATE:
        setCurrentPhase(message.payload.current_phase as Phase)
        setIterationCount(message.payload.iteration_count)
        if (message.payload.attack_path_type) {
          setAttackPathType(message.payload.attack_path_type)
        }
        break

      case MessageType.TODO_UPDATE:
        setTodoList(message.payload.todo_list)
        // Update the last thinking item with the new todo list
        setChatItems(prev => {
          if (prev.length === 0) return prev
          const lastItem = prev[prev.length - 1]
          if ('type' in lastItem && lastItem.type === 'thinking') {
            return [
              ...prev.slice(0, -1),
              { ...lastItem, updated_todo_list: message.payload.todo_list }
            ]
          }
          return prev
        })
        break

      case MessageType.APPROVAL_REQUEST:
        // Ignore duplicate approval requests if we're already awaiting or just processed one
        if (awaitingApprovalRef.current || isProcessingApproval.current) {
          console.log('Ignoring duplicate approval request - already processing')
          break
        }

        console.log('Received approval request:', message.payload)
        awaitingApprovalRef.current = true
        setAwaitingApproval(true)
        setApprovalRequest(message.payload)
        setIsLoading(false)
        break

      case MessageType.QUESTION_REQUEST:
        // Ignore duplicate question requests if we're already awaiting or just processed one
        if (awaitingQuestionRef.current || isProcessingQuestion.current) {
          console.log('Ignoring duplicate question request - already processing')
          break
        }

        console.log('Received question request:', message.payload)
        awaitingQuestionRef.current = true
        setAwaitingQuestion(true)
        setQuestionRequest(message.payload)
        setIsLoading(false)
        break

      case MessageType.RESPONSE:
        // Add agent response message with tier-aware badge
        const tier = message.payload.response_tier || (message.payload.task_complete ? 'full_report' : 'conversational')
        const assistantMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: message.payload.answer,
          phase: message.payload.phase as Phase,
          timestamp: new Date(),
          isReport: tier === 'full_report',
          responseTier: tier,
        }
        setChatItems(prev => [...prev, assistantMessage])
        setIsLoading(false)
        break

      case MessageType.ERROR:
        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: 'An error occurred while processing your request.',
          error: message.payload.message,
          timestamp: new Date(),
        }
        setChatItems(prev => [...prev, errorMessage])
        setIsLoading(false)
        break

      case MessageType.TASK_COMPLETE:
        const completeMessage: Message = {
          id: `complete-${Date.now()}`,
          role: 'assistant',
          content: message.payload.message,
          phase: message.payload.final_phase as Phase,
          timestamp: new Date(),
        }
        setChatItems(prev => [...prev, completeMessage])
        setIsLoading(false)
        break

      case MessageType.GUIDANCE_ACK:
        // Already shown in chat from handleSend
        break

      case MessageType.STOPPED:
        setIsLoading(false)
        setIsStopped(true)
        break

      case MessageType.FILE_READY:
        const fileItem: FileDownloadItem = {
          type: 'file_download',
          id: `file-${Date.now()}`,
          timestamp: new Date(),
          filepath: message.payload.filepath,
          filename: message.payload.filename,
          description: message.payload.description,
          source: message.payload.source,
        }
        setChatItems(prev => [...prev, fileItem])
        break
    }
  }, [todoList])

  // Initialize WebSocket
  const { status, isConnected, reconnectAttempt, sendQuery, sendApproval, sendAnswer, sendGuidance, sendStop, sendResume } = useAgentWebSocket({
    userId: userId || process.env.NEXT_PUBLIC_USER_ID || 'default_user',
    projectId: projectId || process.env.NEXT_PUBLIC_PROJECT_ID || 'default_project',
    sessionId: sessionId || process.env.NEXT_PUBLIC_SESSION_ID || 'default_session',
    enabled: isOpen,
    onMessage: handleWebSocketMessage,
    onError: (error) => {
      // Only show connection errors once, not for every retry
      if (error.message === 'Initial connection failed') {
        const errorMsg: Message = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: `Failed to connect to agent. Please check that the backend is running at ws://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:8090/ws/agent`,
          error: error.message,
          timestamp: new Date(),
        }
        setChatItems(prev => [...prev, errorMsg])
      }
    },
  })

  const handleSend = useCallback(async () => {
    const question = inputValue.trim()
    if (!question || !isConnected || awaitingApproval || awaitingQuestion) return

    // Auto-create conversation on first user message
    if (!conversationId && projectId && userId && sessionId) {
      const conv = await createConversation(sessionId)
      if (conv) {
        setConversationId(conv.id)
        // Title will be set by the backend persistence layer
      }
    }

    if (isLoading) {
      // Agent is working → send as guidance
      const guidanceMessage: Message = {
        id: `guidance-${Date.now()}`,
        role: 'user',
        content: question,
        isGuidance: true,
        timestamp: new Date(),
      }
      setChatItems(prev => [...prev, guidanceMessage])
      setInputValue('')
      sendGuidance(question)
      saveMessage('guidance', { content: question, isGuidance: true })
    } else {
      // Normal query
      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: question,
        timestamp: new Date(),
      }
      setChatItems(prev => [...prev, userMessage])
      setInputValue('')
      setIsLoading(true)

      // Set title from first user message
      const hasUserMessage = chatItems.some((item: ChatItem) => 'role' in item && item.role === 'user')
      if (!hasUserMessage) {
        updateConvMeta({ title: question.substring(0, 100) })
      }

      try {
        sendQuery(question)
      } catch (error) {
        setIsLoading(false)
      }
    }
  }, [inputValue, isConnected, isLoading, awaitingApproval, awaitingQuestion, sendQuery, sendGuidance, conversationId, projectId, userId, sessionId, createConversation, saveMessage, updateConvMeta, chatItems])

  const handleApproval = useCallback((decision: 'approve' | 'modify' | 'abort') => {
    // Prevent double submission using ref (immediate check, not async state)
    if (!awaitingApproval || isProcessingApproval.current || !awaitingApprovalRef.current) {
      return
    }

    // Mark as processing immediately
    isProcessingApproval.current = true
    awaitingApprovalRef.current = false

    setAwaitingApproval(false)
    setApprovalRequest(null)
    setIsLoading(true)

    // Add decision message
    const decisionMessage: Message = {
      id: `decision-${Date.now()}`,
      role: 'user',
      content: decision === 'approve'
        ? 'Approved phase transition'
        : decision === 'modify'
        ? `Modified: ${modificationText}`
        : 'Aborted phase transition',
      timestamp: new Date(),
    }
    setChatItems(prev => [...prev, decisionMessage])

    try {
      sendApproval(decision, decision === 'modify' ? modificationText : undefined)
      setModificationText('')
    } catch (error) {
      setIsLoading(false)
      awaitingApprovalRef.current = false
      isProcessingApproval.current = false
    } finally {
      // Reset the processing flag after a delay to prevent backend from sending duplicate
      setTimeout(() => {
        isProcessingApproval.current = false
      }, 1000)
    }
  }, [modificationText, sendApproval, awaitingApproval])

  const handleAnswer = useCallback(() => {
    // Prevent double submission using ref (immediate check, not async state)
    if (!awaitingQuestion || isProcessingQuestion.current || !awaitingQuestionRef.current) {
      return
    }

    if (!questionRequest) return

    // Mark as processing immediately
    isProcessingQuestion.current = true
    awaitingQuestionRef.current = false

    setAwaitingQuestion(false)
    setQuestionRequest(null)
    setIsLoading(true)

    const answer = questionRequest.format === 'text'
      ? answerText
      : selectedOptions.join(', ')

    // Add answer message
    const answerMessage: Message = {
      id: `answer-${Date.now()}`,
      role: 'user',
      content: `Answer: ${answer}`,
      timestamp: new Date(),
    }
    setChatItems(prev => [...prev, answerMessage])

    try {
      sendAnswer(answer)
      setAnswerText('')
      setSelectedOptions([])
    } catch (error) {
      setIsLoading(false)
      awaitingQuestionRef.current = false
      isProcessingQuestion.current = false
    } finally {
      // Reset the processing flag after a delay to prevent backend from sending duplicate
      setTimeout(() => {
        isProcessingQuestion.current = false
      }, 1000)
    }
  }, [questionRequest, answerText, selectedOptions, sendAnswer, awaitingQuestion])

  const handleStop = useCallback(() => {
    sendStop()
  }, [sendStop])

  const handleResume = useCallback(() => {
    sendResume()
    setIsStopped(false)
    setIsLoading(true)
  }, [sendResume])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
  }

  const handleDownloadMarkdown = useCallback(() => {
    if (chatItems.length === 0) return

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    const lines: string[] = []

    // Header
    lines.push('# AI Agent Session Report')
    lines.push('')
    lines.push(`**Date:** ${new Date().toLocaleString()}  `)
    lines.push(`**Phase:** ${PHASE_CONFIG[currentPhase].label}  `)
    if (iterationCount > 0) lines.push(`**Step:** ${iterationCount}  `)
    if (modelName) lines.push(`**Model:** ${formatModelDisplay(modelName)}  `)
    lines.push('')
    lines.push('---')
    lines.push('')

    // Todo list snapshot
    if (todoList.length > 0) {
      lines.push('## Task List')
      lines.push('')
      todoList.forEach((item: TodoItem) => {
        const icon = item.status === 'completed' ? '[x]' : item.status === 'in_progress' ? '[-]' : '[ ]'
        const desc = item.description || item.content || item.activeForm || 'No description'
        lines.push(`- ${icon} ${desc}`)
      })
      lines.push('')
      lines.push('---')
      lines.push('')
    }

    // Chat timeline
    lines.push('## Session Timeline')
    lines.push('')

    chatItems.forEach(item => {
      if ('role' in item) {
        // Message
        const time = item.timestamp.toLocaleTimeString()
        if (item.role === 'user') {
          lines.push(`### User  \`${time}\``)
          if (item.isGuidance) lines.push('> *[Guidance]*')
        } else {
          lines.push(`### Assistant  \`${time}\``)
          if (item.responseTier === 'full_report') lines.push('> **[Report]**')
          else if (item.responseTier === 'summary') lines.push('> **[Summary]**')
        }
        lines.push('')
        lines.push(item.content)
        lines.push('')
        if (item.error) {
          lines.push(`> **Error:** ${item.error}`)
          lines.push('')
        }
        lines.push('---')
        lines.push('')
      } else if (item.type === 'thinking') {
        const time = item.timestamp.toLocaleTimeString()
        lines.push(`### Thinking  \`${time}\``)
        lines.push('')
        if (item.thought) {
          lines.push(`> ${item.thought}`)
          lines.push('')
        }
        if (item.reasoning) {
          lines.push('<details>')
          lines.push('<summary>Reasoning</summary>')
          lines.push('')
          lines.push(item.reasoning)
          lines.push('')
          lines.push('</details>')
          lines.push('')
        }
        if (item.updated_todo_list && item.updated_todo_list.length > 0) {
          lines.push('<details>')
          lines.push('<summary>Todo List Update</summary>')
          lines.push('')
          item.updated_todo_list.forEach(todo => {
            const icon = todo.status === 'completed' ? '[x]' : todo.status === 'in_progress' ? '[-]' : '[ ]'
            const desc = todo.description || todo.content || todo.activeForm || ''
            lines.push(`- ${icon} ${desc}`)
          })
          lines.push('')
          lines.push('</details>')
          lines.push('')
        }
        lines.push('---')
        lines.push('')
      } else if (item.type === 'tool_execution') {
        const time = item.timestamp.toLocaleTimeString()
        const statusIcon = item.status === 'success' ? 'OK' : item.status === 'error' ? 'FAIL' : 'RUNNING'
        lines.push(`### Tool: \`${item.tool_name}\`  \`${time}\`  [${statusIcon}]`)
        lines.push('')

        // Arguments
        if (item.tool_args && Object.keys(item.tool_args).length > 0) {
          lines.push('**Arguments**')
          lines.push('')
          Object.entries(item.tool_args).forEach(([key, value]) => {
            lines.push(`- **${key}:** \`${typeof value === 'string' ? value : JSON.stringify(value)}\``)
          })
          lines.push('')
        }

        // Raw Output
        const rawOutput = item.output_chunks.join('')
        if (rawOutput) {
          lines.push('<details>')
          lines.push('<summary>Raw Output</summary>')
          lines.push('')
          lines.push('```')
          lines.push(rawOutput)
          lines.push('```')
          lines.push('')
          lines.push('</details>')
          lines.push('')
        }

        // Analysis
        if (item.final_output) {
          lines.push('**Analysis**')
          lines.push('')
          lines.push(item.final_output)
          lines.push('')
        }

        // Actionable Findings
        if (item.actionable_findings && item.actionable_findings.length > 0) {
          lines.push('**Actionable Findings**')
          lines.push('')
          item.actionable_findings.forEach(f => lines.push(`- ${f}`))
          lines.push('')
        }

        // Recommended Next Steps
        if (item.recommended_next_steps && item.recommended_next_steps.length > 0) {
          lines.push('**Recommended Next Steps**')
          lines.push('')
          item.recommended_next_steps.forEach(s => lines.push(`- ${s}`))
          lines.push('')
        }

        lines.push('---')
        lines.push('')
      } else if (item.type === 'file_download') {
        const time = item.timestamp.toLocaleTimeString()
        lines.push(`### File Download  \`${time}\``)
        lines.push('')
        lines.push(`- **File:** ${item.filename}`)
        lines.push(`- **Path:** \`${item.filepath}\``)
        lines.push(`- **Source:** ${item.source}`)
        lines.push(`- **Description:** ${item.description}`)
        lines.push('')
        lines.push('---')
        lines.push('')
      }
    })

    // Download
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `redamon-session-${timestamp}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [chatItems, currentPhase, iterationCount, modelName, todoList])

  const handleNewChat = useCallback(() => {
    // Don't stop the running agent — let it continue in background
    // and persist messages via the backend persistence layer
    setChatItems([])
    setCurrentPhase('informational')
    setAttackPathType('cve_exploit')
    setIterationCount(0)
    setAwaitingApproval(false)
    setApprovalRequest(null)
    setAwaitingQuestion(false)
    setQuestionRequest(null)
    setAnswerText('')
    setSelectedOptions([])
    setTodoList([])
    setIsStopped(false)
    setIsLoading(false)
    awaitingApprovalRef.current = false
    isProcessingApproval.current = false
    awaitingQuestionRef.current = false
    isProcessingQuestion.current = false
    shouldAutoScroll.current = true
    setConversationId(null)
    setShowHistory(false)
    onResetSession?.()
  }, [onResetSession])

  // Switch to a different conversation from history
  const handleSelectConversation = useCallback(async (conv: Conversation) => {
    const full = await loadConversation(conv.id)
    if (!full) return

    // Restore chat items from persisted messages
    let lastTodoList: TodoItem[] = []
    let lastApprovalRequest: any = null
    let lastQuestionRequest: any = null
    // Track whether the agent did actual WORK after the last approval/question.
    // assistant_message doesn't count (it's the phase transition description that
    // arrives alongside the approval_request). Only thinking/tool_start indicate
    // the user already responded and the agent continued.
    let hasWorkAfterApproval = false
    let hasWorkAfterQuestion = false

    const restored: ChatItem[] = full.messages.map((msg: { id: string; type: string; data: unknown; createdAt: string }) => {
      const data = msg.data as any

      // Track agent work after approval/question requests
      if (msg.type === 'thinking' || msg.type === 'tool_start' || msg.type === 'tool_complete') {
        if (lastApprovalRequest) hasWorkAfterApproval = true
        if (lastQuestionRequest) hasWorkAfterQuestion = true
      }

      if (msg.type === 'user_message' || msg.type === 'assistant_message') {
        const restoredTier = data.response_tier || (data.task_complete ? 'full_report' : undefined)
        return {
          id: msg.id,
          role: msg.type === 'user_message' ? 'user' : 'assistant',
          content: data.content || '',
          phase: data.phase,
          timestamp: new Date(msg.createdAt),
          isGuidance: data.isGuidance || false,
          isReport: restoredTier === 'full_report' || (!data.response_tier && (data.isReport || data.task_complete || false)),
          responseTier: restoredTier,
          error: data.error || null,
        } as Message
      } else if (msg.type === 'thinking') {
        return {
          type: 'thinking',
          id: msg.id,
          timestamp: new Date(msg.createdAt),
          thought: data.thought || '',
          reasoning: data.reasoning || '',
          action: 'thinking',
          updated_todo_list: [],
        } as ThinkingItem
      } else if (msg.type === 'tool_start') {
        // Skip tool_start — full data is in tool_complete
        return null
      } else if (msg.type === 'tool_complete') {
        // Reconstruct full ToolExecutionItem with raw output and tool_args
        const rawOutput = data.raw_output || ''
        return {
          type: 'tool_execution',
          id: msg.id,
          timestamp: new Date(msg.createdAt),
          tool_name: data.tool_name || '',
          tool_args: data.tool_args || {},
          status: data.success ? 'success' : 'error',
          output_chunks: rawOutput ? [rawOutput] : [],
          final_output: data.output_summary,
          actionable_findings: data.actionable_findings || [],
          recommended_next_steps: data.recommended_next_steps || [],
        } as ToolExecutionItem
      } else if (msg.type === 'error') {
        return {
          id: msg.id,
          role: 'assistant',
          content: 'An error occurred while processing your request.',
          error: data.message,
          timestamp: new Date(msg.createdAt),
        } as Message
      } else if (msg.type === 'task_complete') {
        return {
          id: msg.id,
          role: 'assistant',
          content: data.message || '',
          phase: data.final_phase,
          timestamp: new Date(msg.createdAt),
        } as Message
      } else if (msg.type === 'guidance') {
        return {
          id: msg.id,
          role: 'user',
          content: data.content || '',
          isGuidance: true,
          timestamp: new Date(msg.createdAt),
        } as Message
      } else if (msg.type === 'file_ready') {
        return {
          type: 'file_download',
          id: msg.id,
          timestamp: new Date(msg.createdAt),
          filepath: data.filepath || '',
          filename: data.filename || '',
          description: data.description || '',
          source: data.source || '',
        } as FileDownloadItem
      } else if (msg.type === 'todo_update') {
        // Track last todo list for state restoration (not a chat item)
        lastTodoList = data.todo_list || []
        return null
      } else if (msg.type === 'phase_update') {
        // Phase updates are metadata, not chat items
        return null
      } else if (msg.type === 'approval_request') {
        lastApprovalRequest = data
        hasWorkAfterApproval = false
        return null
      } else if (msg.type === 'question_request') {
        lastQuestionRequest = data
        hasWorkAfterQuestion = false
        return null
      }
      // Skip unknown types
      return null
    }).filter((item): item is ChatItem => item !== null)

    // Apply state
    setChatItems(restored)
    setConversationId(conv.id)
    setCurrentPhase((conv.currentPhase || 'informational') as Phase)
    setIterationCount(conv.iterationCount || 0)
    setIsLoading(conv.agentRunning)
    setIsStopped(false)
    setTodoList(lastTodoList)
    shouldAutoScroll.current = true
    setShowHistory(false)

    // Restore pending approval/question state if not yet acted upon.
    // The agent is NOT "running" while waiting — it finishes its task and waits
    // for the user to respond. So we check for agent work, not agentRunning.
    if (lastApprovalRequest && !hasWorkAfterApproval) {
      setAwaitingApproval(true)
      setApprovalRequest(lastApprovalRequest)
      awaitingApprovalRef.current = true
    } else {
      setAwaitingApproval(false)
      setApprovalRequest(null)
    }
    if (lastQuestionRequest && !hasWorkAfterQuestion) {
      setAwaitingQuestion(true)
      setQuestionRequest(lastQuestionRequest)
      awaitingQuestionRef.current = true
    } else {
      setAwaitingQuestion(false)
      setQuestionRequest(null)
    }

    // Switch WebSocket session — flag to prevent the sessionId useEffect from clearing state
    isRestoringConversation.current = true
    onSwitchSession?.(conv.sessionId)
  }, [loadConversation, onSwitchSession])

  const handleHistoryNewChat = () => {
    setShowHistory(false)
    handleNewChat()
  }

  const handleDeleteConversation = useCallback(async (id: string) => {
    await deleteConversation(id)
    onRefetchGraph?.()
    // If we just deleted the active conversation, reset to a clean state
    if (id === conversationId) {
      handleNewChat()
    }
  }, [deleteConversation, onRefetchGraph, conversationId, handleNewChat])

  const PhaseIcon = PHASE_CONFIG[currentPhase].icon

  // Connection status indicator with color
  const getConnectionStatusColor = () => {
    return status === ConnectionStatus.CONNECTED ? '#10b981' : '#ef4444' // green : red
  }

  const getConnectionStatusIcon = () => {
    const color = getConnectionStatusColor()
    if (status === ConnectionStatus.CONNECTED) {
      return <Wifi size={12} className={styles.connectionIcon} style={{ color }} />
    } else if (status === ConnectionStatus.RECONNECTING) {
      return <Loader2 size={12} className={`${styles.connectionIcon} ${styles.spinner}`} style={{ color }} />
    } else {
      return <WifiOff size={12} className={styles.connectionIcon} style={{ color }} />
    }
  }

  const getConnectionStatusText = () => {
    switch (status) {
      case ConnectionStatus.CONNECTING:
        return 'Connecting...'
      case ConnectionStatus.CONNECTED:
        return 'Connected'
      case ConnectionStatus.RECONNECTING:
        return `Reconnecting... (${reconnectAttempt}/5)`
      case ConnectionStatus.FAILED:
        return 'Connection failed'
      case ConnectionStatus.DISCONNECTED:
        return 'Disconnected'
    }
  }

  // Group timeline items by their sequence (between messages)
  const groupedChatItems: Array<{ type: 'message' | 'timeline' | 'file_download', content: Message | Array<ThinkingItem | ToolExecutionItem> | FileDownloadItem }> = []

  let currentTimelineGroup: Array<ThinkingItem | ToolExecutionItem> = []

  chatItems.forEach((item) => {
    if ('role' in item) {
      // It's a message - push any accumulated timeline items first
      if (currentTimelineGroup.length > 0) {
        groupedChatItems.push({ type: 'timeline', content: currentTimelineGroup })
        currentTimelineGroup = []
      }
      // Then push the message
      groupedChatItems.push({ type: 'message', content: item })
    } else if ('type' in item && item.type === 'file_download') {
      // File download cards are standalone (not grouped into timeline)
      if (currentTimelineGroup.length > 0) {
        groupedChatItems.push({ type: 'timeline', content: currentTimelineGroup })
        currentTimelineGroup = []
      }
      groupedChatItems.push({ type: 'file_download', content: item })
    } else if ('type' in item && (item.type === 'thinking' || item.type === 'tool_execution')) {
      // It's a timeline item - add to current group
      currentTimelineGroup.push(item)
    }
  })

  // Push any remaining timeline items
  if (currentTimelineGroup.length > 0) {
    groupedChatItems.push({ type: 'timeline', content: currentTimelineGroup })
  }

  const handleCopyMessage = useCallback((messageId: string, content: string) => {
    navigator.clipboard.writeText(content).then(() => {
      setCopiedMessageId(messageId)
      setTimeout(() => setCopiedMessageId(null), 2000)
    })
  }, [])

  const handleCopyField = useCallback((key: string, text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedFieldKey(key)
      setTimeout(() => setCopiedFieldKey(null), 2000)
    })
  }, [])

  const renderMessage = (item: Message) => {
    return (
      <div
        key={item.id}
        className={`${styles.message} ${
          item.role === 'user' ? styles.messageUser : styles.messageAssistant
        } ${item.isGuidance ? styles.messageGuidance : ''}`}
      >
        <div className={styles.messageIcon}>
          {item.role === 'user' ? <User size={14} /> : <Bot size={14} />}
        </div>
        <div className={styles.messageContent}>
          {item.isGuidance && (
            <span className={styles.guidanceBadge}>Guidance</span>
          )}
          {item.responseTier === 'full_report' && (
            <div className={styles.reportHeader}>
              <span className={styles.reportBadge}>Report</span>
            </div>
          )}
          {item.responseTier === 'summary' && (
            <div className={styles.reportHeader}>
              <span className={styles.summaryBadge}>Summary</span>
            </div>
          )}
          <div
            className={styles.messageText}
            {...(item.responseTier === 'full_report' || item.responseTier === 'summary' ? { 'data-report-content': true } : {})}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || '')
                  const language = match ? match[1] : ''
                  const isInline = !className
                  const codeText = String(children).replace(/\n$/, '')

                  if (!isInline) {
                    const codeKey = `code-${item.id}-${codeText.slice(0, 20)}`
                    return (
                      <div className={styles.codeBlockWrapper}>
                        <button
                          className={`${styles.codeBlockCopyButton} ${copiedFieldKey === codeKey ? styles.codeBlockCopyButtonCopied : ''}`}
                          onClick={() => handleCopyField(codeKey, codeText)}
                          title="Copy code"
                        >
                          {copiedFieldKey === codeKey ? <Check size={11} /> : <Copy size={11} />}
                        </button>
                        {language ? (
                          <SyntaxHighlighter
                            style={vscDarkPlus as any}
                            language={language}
                            PreTag="div"
                          >
                            {codeText}
                          </SyntaxHighlighter>
                        ) : (
                          <pre><code className={className} {...props}>{children}</code></pre>
                        )}
                      </div>
                    )
                  }

                  return (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  )
                },
                td({ children, ...props }: any) {
                  const text = extractTextFromChildren(children)
                  if (!text || text.length < 3) {
                    return <td {...props}>{children}</td>
                  }
                  const cellKey = `td-${item.id}-${text.slice(0, 30)}`
                  return (
                    <td {...props}>
                      <span className={styles.tableCellContent}>
                        {children}
                        <button
                          className={`${styles.tableCellCopyButton} ${copiedFieldKey === cellKey ? styles.tableCellCopyButtonCopied : ''}`}
                          onClick={() => handleCopyField(cellKey, text)}
                          title="Copy value"
                        >
                          {copiedFieldKey === cellKey ? <Check size={10} /> : <Copy size={10} />}
                        </button>
                      </span>
                    </td>
                  )
                },
              }}
            >
              {item.content}
            </ReactMarkdown>
          </div>

          {item.role === 'assistant' && !item.isGuidance && (
            <button
              className={`${styles.copyButton} ${copiedMessageId === item.id ? styles.copyButtonCopied : ''}`}
              onClick={() => handleCopyMessage(item.id, item.content)}
              title="Copy to clipboard"
            >
              {copiedMessageId === item.id ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
            </button>
          )}

          {item.error && (
            <div className={styles.errorBadge}>
              <AlertCircle size={12} />
              <span>{item.error}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div
      className={`${styles.drawer} ${isOpen ? styles.drawerOpen : ''}`}
      aria-hidden={!isOpen}
    >
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.headerIcon}>
            <Bot size={16} />
          </div>
          <div className={styles.headerText}>
            <h2 className={styles.title}>AI Agent</h2>
            <div className={styles.connectionStatus}>
              {getConnectionStatusIcon()}
              <span className={styles.subtitle} style={{ color: getConnectionStatusColor() }}>
                {getConnectionStatusText()}
              </span>
              <span className={styles.sessionCode} title={sessionId}>
                Session: {sessionId.slice(-8)}
              </span>
            </div>
          </div>
        </div>
        <div className={styles.headerActions}>
          {hasOtherChains && onToggleOtherChains && (
            <button
              className={`${styles.iconButton} ${isOtherChainsHidden ? styles.iconButtonActive : ''}`}
              onClick={onToggleOtherChains}
              title={isOtherChainsHidden ? 'Show all sessions in graph' : 'Show only this session in graph'}
              aria-label={isOtherChainsHidden ? 'Show all sessions in graph' : 'Show only this session in graph'}
            >
              {isOtherChainsHidden ? <Eye size={14} /> : <EyeOff size={14} />}
            </button>
          )}
          <button
            className={styles.iconButton}
            onClick={() => setShowHistory(!showHistory)}
            title="Session history"
            aria-label="Session history"
          >
            <History size={14} />
          </button>
          <button
            className={styles.iconButton}
            onClick={handleNewChat}
            title="New session"
            aria-label="Start new session"
          >
            <Plus size={14} />
          </button>
          <button
            className={styles.iconButton}
            onClick={handleDownloadMarkdown}
            title="Download chat as Markdown"
            aria-label="Download chat as Markdown"
            disabled={chatItems.length === 0}
          >
            <Download size={14} />
          </button>
          <button
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Close assistant"
          >
            &times;
          </button>
        </div>
      </div>

      {/* Session History Panel */}
      {showHistory && (
        <ConversationHistory
          conversations={conversations}
          currentSessionId={sessionId}
          onBack={() => setShowHistory(false)}
          onSelect={handleSelectConversation}
          onDelete={handleDeleteConversation}
          onNewChat={handleHistoryNewChat}
        />
      )}

      {/* Phase Indicator */}
      <div className={styles.phaseIndicator}>
        <div
          className={styles.phaseBadge}
          style={{
            backgroundColor: PHASE_CONFIG[currentPhase].bgColor,
            borderColor: PHASE_CONFIG[currentPhase].color,
          }}
        >
          <PhaseIcon size={14} style={{ color: PHASE_CONFIG[currentPhase].color }} />
          <span style={{ color: PHASE_CONFIG[currentPhase].color }}>
            {PHASE_CONFIG[currentPhase].label}
          </span>
        </div>

        {/* Phase Tools Icon */}
        {toolPhaseMap && (() => {
          const phaseTools = Object.entries(toolPhaseMap)
            .filter(([, phases]) => phases.includes(currentPhase))
            .map(([name]) => name)
          return phaseTools.length > 0 ? (
            <Tooltip
              position="bottom"
              content={
                <div className={styles.phaseToolsTooltip}>
                  <div className={styles.phaseToolsHeader}>Phase Tools</div>
                  {phaseTools.map(t => (
                    <div key={t} className={styles.phaseToolsItem}>{t}</div>
                  ))}
                </div>
              }
            >
              <Wrench
                size={13}
                className={styles.phaseToolsIcon}
              />
            </Tooltip>
          ) : null
        })()}

        {/* Attack Path Badge - Show when in exploitation or post_exploitation phase */}
        {(currentPhase === 'exploitation' || currentPhase === 'post_exploitation') && (
          <div
            className={styles.phaseBadge}
            style={{
              backgroundColor: getAttackPathConfig(attackPathType).bgColor,
              borderColor: getAttackPathConfig(attackPathType).color,
            }}
          >
            <span style={{ color: getAttackPathConfig(attackPathType).color }}>
              {getAttackPathConfig(attackPathType).shortLabel}
            </span>
          </div>
        )}

        {iterationCount > 0 && (
          <span className={styles.iterationCount}>Step {iterationCount}</span>
        )}

        {onToggleStealth ? (
          <button
            className={`${styles.stealthToggle} ${stealthMode ? styles.stealthToggleActive : ''}`}
            onClick={() => onToggleStealth(!stealthMode)}
            title={stealthMode
              ? 'Stealth Mode ON — click to disable'
              : 'Stealth Mode OFF — click to enable passive-only techniques'
            }
          >
            <StealthIcon size={11} />
            <span>STEALTH</span>
          </button>
        ) : stealthMode ? (
          <span className={styles.stealthBadge} title="Stealth Mode — passive/low-noise techniques only">
            <StealthIcon size={11} />
          </span>
        ) : null}

        {modelName && (
          <span className={styles.modelBadge}>{formatModelDisplay(modelName)}</span>
        )}
      </div>

      {/* Todo List Widget */}
      {todoList.length > 0 && (
        <div className={styles.todoWidgetContainer}>
          <TodoListWidget items={todoList} />
        </div>
      )}

      {/* Unified Chat (Messages + Timeline Items) */}
      <div className={styles.messages} ref={messagesContainerRef} onScroll={checkIfAtBottom}>
        {chatItems.length === 0 && (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <img src="/logo.png" alt="RedAmon" width={72} height={72} style={{ objectFit: 'contain' }} />
            </div>
            <h3 className={styles.emptyTitle}>How can I help you?</h3>
            <p className={styles.emptyDescription}>
              Ask me about recon data, vulnerabilities, exploitation, or post-exploitation activities.
            </p>
            <div className={styles.templateGroups}>
              {/* Informational */}
              <div className={styles.templateGroup}>
                <button
                  className={`${styles.templateGroupHeader} ${openTemplateGroup === 'informational' ? styles.templateGroupHeaderOpen : ''}`}
                  onClick={() => setOpenTemplateGroup((prev: string | null) => prev === 'informational' ? null : 'informational')}
                  style={{ '--tg-color': 'var(--text-tertiary)' } as React.CSSProperties}
                >
                  <Shield size={14} />
                  <span>Informational</span>
                  <ChevronDown size={14} className={styles.templateGroupChevron} />
                </button>
                {openTemplateGroup === 'informational' && (
                  <div className={styles.templateGroupItems}>
                    <button className={styles.suggestion} onClick={() => setInputValue('Map the attack surface: list all domains, subdomains, IPs, open ports, and services discovered')} disabled={!isConnected}>
                      Map the full attack surface
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Which vulnerabilities have known Metasploit exploit modules available?')} disabled={!isConnected}>
                      Find exploitable CVEs with Metasploit modules
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Were any credentials, API keys, or secrets leaked in GitHub repositories?')} disabled={!isConnected}>
                      Check for leaked secrets on GitHub
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Are any CISA Known Exploited Vulnerabilities (KEV) present in the scan results?')} disabled={!isConnected}>
                      Find CISA Known Exploited Vulnerabilities
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('What web endpoints, parameters, and forms were discovered by the crawler?')} disabled={!isConnected}>
                      Show discovered web endpoints and parameters
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Give me a prioritized risk summary of all findings ranked by severity and exploitability')} disabled={!isConnected}>
                      Prioritized risk summary
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('What technology versions were detected, and which ones have known CVEs?')} disabled={!isConnected}>
                      Detect outdated technologies with known CVEs
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Which services expose authentication that could be tested with credential brute force?')} disabled={!isConnected}>
                      Find brute-forceable services
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Analyze TLS certificates and HTTP security headers for misconfigurations')} disabled={!isConnected}>
                      Analyze TLS and security headers
                    </button>
                  </div>
                )}
              </div>

              {/* Exploitation */}
              <div className={styles.templateGroup}>
                <button
                  className={`${styles.templateGroupHeader} ${openTemplateGroup === 'exploitation' ? styles.templateGroupHeaderOpen : ''}`}
                  onClick={() => setOpenTemplateGroup((prev: string | null) => prev === 'exploitation' ? null : 'exploitation')}
                  style={{ '--tg-color': 'var(--status-warning)' } as React.CSSProperties}
                >
                  <Target size={14} />
                  <span>Exploitation</span>
                  <ChevronDown size={14} className={styles.templateGroupChevron} />
                </button>
                {openTemplateGroup === 'exploitation' && (
                  <div className={styles.templateGroupItems}>
                    <button className={styles.suggestion} onClick={() => setInputValue('Find and exploit the most critical CVE affecting the primary target')} disabled={!isConnected}>
                      Exploit the most critical vulnerability
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Find the most critical CVE on the target, exploit it with Metasploit, and open a shell session')} disabled={!isConnected}>
                      Exploit a critical CVE and open a session
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Brute force SSH credentials on the target, then list sensitive files and directories')} disabled={!isConnected}>
                      Brute force SSH and explore the server
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Use any secrets or credentials found on GitHub to attempt access to the target server and report what you find')} disabled={!isConnected}>
                      Leverage GitHub secrets to access the server
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Test for SQL injection on discovered web forms and parameters, then extract database contents')} disabled={!isConnected}>
                      Exploit SQL injection on web forms
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Attempt to exploit default or weak credentials on all discovered login panels, admin interfaces, and services')} disabled={!isConnected}>
                      Test default credentials on all services
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Upload a web shell to the target server through a file upload vulnerability and gain remote command execution')} disabled={!isConnected}>
                      Upload a web shell via file upload vulnerability
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Chain multiple low-severity findings together to achieve remote code execution on the target')} disabled={!isConnected}>
                      Chain vulnerabilities for RCE
                    </button>
                  </div>
                )}
              </div>

              {/* Social Engineering */}
              <div className={styles.templateGroup}>
                <button
                  className={`${styles.templateGroupHeader} ${openTemplateGroup === 'social_engineering' ? styles.templateGroupHeaderOpen : ''}`}
                  onClick={() => setOpenTemplateGroup((prev: string | null) => prev === 'social_engineering' ? null : 'social_engineering')}
                  style={{ '--tg-color': 'var(--accent-tertiary, #ec4899)' } as React.CSSProperties}
                >
                  <Mail size={14} />
                  <span>Social Engineering</span>
                  <ChevronDown size={14} className={styles.templateGroupChevron} />
                </button>
                {openTemplateGroup === 'social_engineering' && (
                  <div className={styles.templateGroupItems}>
                    {/* ── Windows ── */}
                    <span className={styles.templateOsLabel}>Windows</span>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Windows Meterpreter EXE payload and set up the handler to catch the callback when the victim runs it')} disabled={!isConnected}>
                      Meterpreter EXE (reverse_tcp)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Windows reverse_https Meterpreter EXE payload for encrypted callback that bypasses the victim firewall')} disabled={!isConnected}>
                      Meterpreter EXE (reverse_https)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Windows reverse shell EXE encoded with shikata_ga_nai (5 iterations) for AV evasion on the victim machine and set up the handler')} disabled={!isConnected}>
                      Encoded EXE (shikata_ga_nai AV evasion)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a fileless PowerShell (psh-reflection) Meterpreter payload that runs entirely in memory when the victim executes it')} disabled={!isConnected}>
                      Fileless PowerShell (psh-reflection)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Create a malicious Word document with a VBA macro that opens a Meterpreter session when the victim enables macros')} disabled={!isConnected}>
                      Malicious Word macro document (VBA)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Create a weaponized Excel spreadsheet with a macro payload that establishes a reverse shell when the victim opens it')} disabled={!isConnected}>
                      Malicious Excel macro spreadsheet (VBA)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a trojanized PDF file that executes a reverse shell when the victim opens it in Adobe Reader')} disabled={!isConnected}>
                      Malicious PDF document
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Create a malicious RTF document exploiting CVE-2017-0199 that fetches an HTA payload when the victim opens it')} disabled={!isConnected}>
                      Malicious RTF document (CVE-2017-0199)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a malicious Windows shortcut (LNK file) that executes a reverse shell payload when the victim clicks it')} disabled={!isConnected}>
                      Malicious LNK shortcut file
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Set up a PowerShell web delivery attack and generate a one-liner for the victim to execute to get a Meterpreter session')} disabled={!isConnected}>
                      PowerShell web delivery attack
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Create an HTA delivery server that serves a payload when the victim visits the URL in their browser')} disabled={!isConnected}>
                      HTA delivery server
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Set up a Regsvr32 web delivery attack to bypass AppLocker restrictions when the victim executes the one-liner')} disabled={!isConnected}>
                      Regsvr32 AppLocker bypass
                    </button>

                    {/* ── Linux ── */}
                    <span className={styles.templateOsLabel}>Linux</span>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Linux x64 Meterpreter ELF binary payload and set up the handler to catch the callback when the victim runs it')} disabled={!isConnected}>
                      Meterpreter ELF binary (reverse_tcp)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Linux x64 basic shell ELF binary (linux/x64/shell_reverse_tcp) as a fallback payload for the victim to execute')} disabled={!isConnected}>
                      Shell ELF binary (fallback)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a bash reverse shell one-liner (cmd/unix/reverse_bash) for a Linux victim to execute and set up the handler')} disabled={!isConnected}>
                      Bash reverse shell one-liner
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Python reverse shell one-liner (cmd/unix/reverse_python) for a Linux victim with Python installed and set up the handler')} disabled={!isConnected}>
                      Python reverse shell one-liner
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Set up a Python web delivery attack (exploit/multi/script/web_delivery TARGET 0) and generate a one-liner for a Linux victim to execute')} disabled={!isConnected}>
                      Python web delivery (one-liner)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Linux ELF reverse shell payload encoded with x64/xor for AV evasion on the victim machine and set up the handler')} disabled={!isConnected}>
                      Encoded ELF (x64/xor AV evasion)
                    </button>

                    {/* ── macOS ── */}
                    <span className={styles.templateOsLabel}>macOS</span>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a macOS Mach-O Meterpreter reverse_tcp payload and set up the handler to catch the callback when the victim runs it')} disabled={!isConnected}>
                      Meterpreter Mach-O binary (reverse_tcp)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a macOS Python reverse shell one-liner (cmd/unix/reverse_python) for the victim to execute bypassing Gatekeeper')} disabled={!isConnected}>
                      Python reverse shell (Gatekeeper bypass)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a macOS bash reverse shell one-liner (cmd/unix/reverse_bash) for a macOS victim to execute and set up the handler')} disabled={!isConnected}>
                      Bash reverse shell one-liner
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Set up a Python web delivery attack (exploit/multi/script/web_delivery TARGET 0) and generate a one-liner for a macOS victim to execute')} disabled={!isConnected}>
                      Python web delivery (one-liner)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a macOS Mach-O Meterpreter payload encoded with x64/xor for AV evasion on the victim machine and set up the handler')} disabled={!isConnected}>
                      Encoded Mach-O (x64/xor AV evasion)
                    </button>

                    {/* ── Android ── */}
                    <span className={styles.templateOsLabel}>Android</span>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate an Android APK backdoor with android/meterpreter/reverse_tcp that opens a Meterpreter session when the victim installs it')} disabled={!isConnected}>
                      Meterpreter APK backdoor
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate an Android APK payload and embed it into a legitimate APK using msfvenom -x to trojanize an app the victim will install')} disabled={!isConnected}>
                      Trojanized APK (injected into legit app)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate an Android reverse_https APK payload for encrypted callback that bypasses network inspection on the victim device')} disabled={!isConnected}>
                      APK with reverse_https (encrypted)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate an Android APK payload encoded with x86/shikata_ga_nai for AV evasion on the victim device and set up the handler')} disabled={!isConnected}>
                      Encoded APK (shikata_ga_nai AV evasion)
                    </button>

                    {/* ── Cross-Platform / Java / PHP ── */}
                    <span className={styles.templateOsLabel}>Cross-Platform / Java / PHP</span>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a cross-platform Python Meterpreter payload (python/meterpreter/reverse_tcp) for a victim running Windows, Linux, or macOS')} disabled={!isConnected}>
                      Python Meterpreter (cross-platform)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a Java WAR backdoor for the victim to deploy on a Tomcat or JBoss server and set up the Meterpreter handler')} disabled={!isConnected}>
                      Java WAR backdoor (Tomcat / JBoss)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Set up a PHP web delivery attack (exploit/multi/script/web_delivery TARGET 1) and generate a one-liner for a victim web server running PHP')} disabled={!isConnected}>
                      PHP web delivery (web servers)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Set up a pubprn web delivery attack (exploit/multi/script/web_delivery TARGET 4) and generate a one-liner for the victim to bypass script restrictions')} disabled={!isConnected}>
                      pubprn script bypass (web delivery)
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Set up a SyncAppvPublishingServer web delivery attack (exploit/multi/script/web_delivery TARGET 5) for the victim to bypass Windows restrictions')} disabled={!isConnected}>
                      SyncAppvPublishing bypass (web delivery)
                    </button>

                    {/* ── Email Delivery ── */}
                    <span className={styles.templateOsLabel}>Email Delivery</span>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a phishing payload and send it via email to the victim at target@example.com with a convincing IT support pretext')} disabled={!isConnected}>
                      Send payload via phishing email
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Generate a malicious Office document and send it via email to the victim at target@example.com disguised as an invoice attachment')} disabled={!isConnected}>
                      Send malicious document via email
                    </button>
                  </div>
                )}
              </div>

              {/* Post-Exploitation */}
              <div className={styles.templateGroup}>
                <button
                  className={`${styles.templateGroupHeader} ${openTemplateGroup === 'post_exploitation' ? styles.templateGroupHeaderOpen : ''}`}
                  onClick={() => setOpenTemplateGroup((prev: string | null) => prev === 'post_exploitation' ? null : 'post_exploitation')}
                  style={{ '--tg-color': 'var(--status-error)' } as React.CSSProperties}
                >
                  <Zap size={14} />
                  <span>Post-Exploitation</span>
                  <ChevronDown size={14} className={styles.templateGroupChevron} />
                </button>
                {openTemplateGroup === 'post_exploitation' && (
                  <div className={styles.templateGroupItems}>
                    <button className={styles.suggestion} onClick={() => setInputValue('After gaining access, search for passwords, API keys, config files, and database credentials on the server')} disabled={!isConnected}>
                      Hunt for secrets and credentials on the server
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Dump password hashes from /etc/shadow and attempt to crack them offline')} disabled={!isConnected}>
                      Dump and crack password hashes
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Check for privilege escalation vectors: SUID binaries, sudo misconfigurations, writable cron jobs, and kernel exploits')} disabled={!isConnected}>
                      Find privilege escalation vectors
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Find database credentials on the server, connect to the database, and dump sensitive tables (users, credentials, PII)')} disabled={!isConnected}>
                      Pivot to database and dump sensitive data
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Enumerate network interfaces, ARP tables, and routing to discover internal hosts, then attempt to pivot laterally')} disabled={!isConnected}>
                      Map internal network and pivot laterally
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Enumerate all users on the system, collect SSH keys, bash history, and attempt lateral movement to other hosts')} disabled={!isConnected}>
                      Harvest SSH keys and move laterally
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Establish persistence on the compromised server using a cron job, SSH key, or backdoor user account')} disabled={!isConnected}>
                      Establish persistence on the server
                    </button>
                    <button className={styles.suggestion} onClick={() => setInputValue('Exploit the target web server and replace the homepage with a defacement page as proof of compromise')} disabled={!isConnected}>
                      Deface the target homepage
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Render messages and timeline items in chronological order */}
        {groupedChatItems.map((groupItem, index) => {
          if (groupItem.type === 'message') {
            return renderMessage(groupItem.content as Message)
          } else if (groupItem.type === 'file_download') {
            const file = groupItem.content as FileDownloadItem
            return (
              <FileDownloadCard
                key={file.id}
                filepath={file.filepath}
                filename={file.filename}
                description={file.description}
                source={file.source}
              />
            )
          } else {
            // Render timeline group
            const items = groupItem.content as Array<ThinkingItem | ToolExecutionItem>
            return (
              <AgentTimeline
                key={`timeline-${index}`}
                items={items}
                isStreaming={isLoading && index === groupedChatItems.length - 1}
              />
            )
          }
        })}

        {isLoading && (
          <div className={`${styles.message} ${styles.messageAssistant}`}>
            <div className={styles.messageIcon}>
              <Bot size={14} />
            </div>
            <div className={styles.messageContent}>
              <div className={styles.loadingIndicator}>
                <Loader2 size={14} className={styles.spinner} />
                <span>Processing...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Approval Dialog */}
      {awaitingApproval && approvalRequest && (
        <div className={styles.approvalDialog}>
          <div className={styles.approvalHeader}>
            <AlertCircle size={16} />
            <span>Phase Transition Request</span>
          </div>
          <div className={styles.approvalContent}>
            <p className={styles.approvalTransition}>
              <span className={styles.approvalFrom}>{approvalRequest.from_phase}</span>
              <span className={styles.approvalArrow}>→</span>
              <span className={styles.approvalTo}>{approvalRequest.to_phase}</span>
            </p>

            <div className={styles.approvalDisclaimer}>
              <ShieldAlert size={16} className={styles.approvalDisclaimerIcon} />
              <p className={styles.approvalDisclaimerText}>
                This transition will enable <strong>active operations</strong> against the target.
                By approving, you confirm that you <strong>own the target</strong> or have{' '}
                <strong>explicit written permission</strong> from the owner.
                Unauthorized activity is illegal and may result in criminal penalties.
              </p>
            </div>

            <p className={styles.approvalReason}>{approvalRequest.reason}</p>

            {approvalRequest.planned_actions.length > 0 && (
              <div className={styles.approvalSection}>
                <strong>Planned Actions:</strong>
                <ul>
                  {approvalRequest.planned_actions.map((action, i) => (
                    <li key={i}>{action}</li>
                  ))}
                </ul>
              </div>
            )}

            {approvalRequest.risks.length > 0 && (
              <div className={styles.approvalSection}>
                <strong>Risks:</strong>
                <ul>
                  {approvalRequest.risks.map((risk, i) => (
                    <li key={i}>{risk}</li>
                  ))}
                </ul>
              </div>
            )}

            <textarea
              className={styles.modificationInput}
              placeholder="Optional: provide modification feedback..."
              value={modificationText}
              onChange={(e) => setModificationText(e.target.value)}
            />
          </div>
          <div className={styles.approvalActions}>
            <button
              className={`${styles.approvalButton} ${styles.approvalButtonApprove}`}
              onClick={() => handleApproval('approve')}
              disabled={isLoading}
            >
              Approve
            </button>
            <button
              className={`${styles.approvalButton} ${styles.approvalButtonModify}`}
              onClick={() => handleApproval('modify')}
              disabled={isLoading || !modificationText.trim()}
            >
              Modify
            </button>
            <button
              className={`${styles.approvalButton} ${styles.approvalButtonAbort}`}
              onClick={() => handleApproval('abort')}
              disabled={isLoading}
            >
              Abort
            </button>
          </div>
        </div>
      )}

      {/* Q&A Dialog */}
      {awaitingQuestion && questionRequest && (
        <div className={styles.questionDialog}>
          <div className={styles.questionHeader}>
            <HelpCircle size={16} />
            <span>Agent Question</span>
          </div>
          <div className={styles.questionContent}>
            <div className={styles.questionText}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '')
                    const language = match ? match[1] : ''
                    const isInline = !className

                    return !isInline && language ? (
                      <SyntaxHighlighter
                        style={vscDarkPlus as any}
                        language={language}
                        PreTag="div"
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    ) : (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    )
                  }
                }}
              >
                {questionRequest.question}
              </ReactMarkdown>
            </div>
            {questionRequest.context && (
              <div className={styles.questionContext}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {questionRequest.context}
                </ReactMarkdown>
              </div>
            )}

            {questionRequest.format === 'text' && (
              <textarea
                className={styles.answerInput}
                placeholder={questionRequest.default_value || 'Type your answer...'}
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
              />
            )}

            {questionRequest.format === 'single_choice' && questionRequest.options.length > 0 && (
              <div className={styles.optionsList}>
                {questionRequest.options.map((option, i) => (
                  <label key={i} className={styles.optionRadio}>
                    <input
                      type="radio"
                      name="question-option"
                      value={option}
                      checked={selectedOptions[0] === option}
                      onChange={() => setSelectedOptions([option])}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            )}

            {questionRequest.format === 'multi_choice' && questionRequest.options.length > 0 && (
              <div className={styles.optionsList}>
                {questionRequest.options.map((option, i) => (
                  <label key={i} className={styles.optionCheckbox}>
                    <input
                      type="checkbox"
                      value={option}
                      checked={selectedOptions.includes(option)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedOptions([...selectedOptions, option])
                        } else {
                          setSelectedOptions(selectedOptions.filter(o => o !== option))
                        }
                      }}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <div className={styles.questionActions}>
            <button
              className={`${styles.answerButton} ${styles.answerButtonSubmit}`}
              onClick={handleAnswer}
              disabled={isLoading || (questionRequest.format === 'text' ? !answerText.trim() : selectedOptions.length === 0)}
            >
              Submit Answer
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div className={styles.inputContainer}>
        <div className={styles.inputWrapper}>
          <textarea
            ref={inputRef}
            className={styles.input}
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              !isConnected
                ? 'Connecting to agent...'
                : awaitingApproval
                ? 'Respond to the approval request above...'
                : awaitingQuestion
                ? 'Answer the question above...'
                : isStopped
                ? 'Agent stopped. Click resume to continue...'
                : isLoading
                ? 'Send guidance to the agent...'
                : 'Ask a question...'
            }
            rows={1}
            disabled={awaitingApproval || awaitingQuestion || !isConnected || isStopped}
          />
          <div className={styles.inputActions}>
            {(isLoading || isStopped) && (
              <button
                className={`${styles.stopResumeButton} ${isStopped ? styles.resumeButton : styles.stopButton}`}
                onClick={isStopped ? handleResume : handleStop}
                aria-label={isStopped ? 'Resume agent' : 'Stop agent'}
                title={isStopped ? 'Resume execution' : 'Stop execution'}
              >
                {isStopped ? <Play size={13} /> : <Square size={13} />}
              </button>
            )}
            <button
              className={styles.sendButton}
              onClick={handleSend}
              disabled={!inputValue.trim() || awaitingApproval || awaitingQuestion || !isConnected || isStopped}
              aria-label="Send message"
            >
              <Send size={13} />
            </button>
          </div>
        </div>
        <span className={styles.inputHint}>
          {isConnected
            ? isLoading
              ? 'Send guidance or stop the agent'
              : 'Press Enter to send, Shift+Enter for new line'
            : 'Waiting for connection...'}
        </span>
      </div>
    </div>
  )
}
