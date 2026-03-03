/**
 * WebSocket Message Types and TypeScript Definitions
 *
 * Mirrors the backend Python definitions in agentic/websocket_api.py
 * Ensures type-safe communication between frontend and backend.
 */

// =============================================================================
// MESSAGE TYPES
// =============================================================================

export enum MessageType {
  // Client → Server
  INIT = 'init',
  QUERY = 'query',
  APPROVAL = 'approval',
  ANSWER = 'answer',
  PING = 'ping',
  GUIDANCE = 'guidance',
  STOP = 'stop',
  RESUME = 'resume',

  // Server → Client
  CONNECTED = 'connected',
  THINKING = 'thinking',
  THINKING_CHUNK = 'thinking_chunk',
  TOOL_START = 'tool_start',
  TOOL_OUTPUT_CHUNK = 'tool_output_chunk',
  TOOL_COMPLETE = 'tool_complete',
  PHASE_UPDATE = 'phase_update',
  TODO_UPDATE = 'todo_update',
  APPROVAL_REQUEST = 'approval_request',
  QUESTION_REQUEST = 'question_request',
  RESPONSE = 'response',
  EXECUTION_STEP = 'execution_step',
  ERROR = 'error',
  PONG = 'pong',
  TASK_COMPLETE = 'task_complete',
  GUIDANCE_ACK = 'guidance_ack',
  STOPPED = 'stopped',
  FILE_READY = 'file_ready',
}

// =============================================================================
// CLIENT MESSAGE PAYLOADS (Client → Server)
// =============================================================================

export interface InitPayload {
  user_id: string
  project_id: string
  session_id: string
}

export interface QueryPayload {
  question: string
}

export interface ApprovalPayload {
  decision: 'approve' | 'modify' | 'abort'
  modification?: string
}

export interface AnswerPayload {
  answer: string
}

export interface GuidancePayload {
  message: string
}

export interface GuidanceAckPayload {
  message: string
  queue_position: number
}

export interface StoppedPayload {
  message: string
  iteration: number
  phase: string
}

// =============================================================================
// SERVER MESSAGE PAYLOADS (Server → Client)
// =============================================================================

export interface ConnectedPayload {
  session_id: string
  message: string
  timestamp: string
}

export interface ThinkingPayload {
  iteration: number
  phase: string
  thought: string
  reasoning: string
}

export interface ThinkingChunkPayload {
  chunk: string
}

export interface ToolStartPayload {
  tool_name: string
  tool_args: Record<string, any>
}

export interface ToolOutputChunkPayload {
  tool_name: string
  chunk: string
  is_final: boolean
}

export interface ToolCompletePayload {
  tool_name: string
  success: boolean
  output_summary: string
  actionable_findings: string[]
  recommended_next_steps: string[]
}

export interface PhaseUpdatePayload {
  current_phase: string
  iteration_count: number
  attack_path_type?: string  // "cve_exploit", "brute_force_credential_guess", or "<term>-unclassified"
}

export interface TodoItem {
  id?: string
  description?: string  // Backend uses 'description'
  content?: string      // Keep for backward compatibility
  status: 'pending' | 'in_progress' | 'completed'
  activeForm?: string
  priority?: string
}

export interface TodoUpdatePayload {
  todo_list: TodoItem[]
}

export interface ApprovalRequestPayload {
  from_phase: string
  to_phase: string
  reason: string
  planned_actions: string[]
  risks: string[]
}

export interface QuestionRequestPayload {
  question: string
  context: string
  format: 'text' | 'single_choice' | 'multi_choice'
  options: string[]
  default_value?: string
}

export interface ResponsePayload {
  answer: string
  iteration_count: number
  phase: string
  task_complete: boolean
  response_tier?: 'conversational' | 'summary' | 'full_report'
}

export interface ExecutionStepPayload {
  step: Record<string, any>
}

export interface ErrorPayload {
  message: string
  recoverable: boolean
}

export interface TaskCompletePayload {
  message: string
  final_phase: string
  total_iterations: number
}

export interface FileReadyPayload {
  filepath: string
  filename: string
  source: string
  description: string
}

// =============================================================================
// MESSAGE STRUCTURE
// =============================================================================

export interface ClientMessage<T = any> {
  type: MessageType
  payload: T
}

export interface ServerMessage<T = any> {
  type: MessageType
  payload: T
  timestamp: string
}

// =============================================================================
// WEBSOCKET CONNECTION STATE
// =============================================================================

export enum ConnectionStatus {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  RECONNECTING = 'reconnecting',
  FAILED = 'failed',
}

export interface WebSocketState {
  status: ConnectionStatus
  isConnected: boolean
  reconnectAttempt: number
  error: Error | null
}

// =============================================================================
// ACTIVE SESSIONS (REST polling, not WebSocket)
// =============================================================================

export interface MsfSession {
  id: number
  type: 'meterpreter' | 'shell' | 'unknown'
  info: string
  connection: string
  target_ip: string
  chat_session_id: string | null
}

export interface MsfJob {
  id: number
  name: string
  payload: string
  port: number
}

export interface NonMsfSession {
  id: string
  type: string
  tool: string
  command: string
  chat_session_id: string | null
}

export interface SessionsData {
  sessions: MsfSession[]
  jobs: MsfJob[]
  non_msf_sessions: NonMsfSession[]
  cache_age_seconds: number
  agent_busy: boolean
}

export interface SessionInteractResult {
  busy: boolean
  output?: string
  message?: string
}

// =============================================================================
// TYPE GUARDS (Runtime type checking)
// =============================================================================

export function isServerMessage(data: any): data is ServerMessage {
  return (
    typeof data === 'object' &&
    data !== null &&
    'type' in data &&
    'payload' in data &&
    'timestamp' in data
  )
}

export function isMessageType(type: string): type is MessageType {
  return Object.values(MessageType).includes(type as MessageType)
}
