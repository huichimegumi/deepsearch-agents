export type ConnectionState = "connecting" | "connected" | "reconnecting" | "closed";

export type MonitorEventName =
  | "session_created"
  | "tool_start"
  | "search_status"
  | "assistant_call"
  | "task_result"
  | "task_cancelled"
  | "error"
  | string;

export interface MonitorMessage {
  type: "monitor_event";
  event: MonitorEventName;
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface PongMessage {
  type: "pong";
  message: string;
}

export type SocketMessage = MonitorMessage | PongMessage;

export interface TaskResponse {
  status: "started" | string;
  thread_id: string;
}

export interface CancelTaskResponse {
  status: "cancelled" | "cancelling" | string;
  thread_id: string;
  message?: string;
}

export interface UploadResponse {
  status: "uploaded" | string;
  files: string[];
}

export interface OutputFile {
  name: string;
  type: "file" | string;
  path: string;
  size: number;
  mtime: number;
}

export interface FileListResponse {
  files?: OutputFile[];
  error?: string;
}

export interface UploadedItem {
  uid: string;
  name: string;
  size: number;
  raw: File;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: "pending" | "indexing" | "ready" | "failed" | string;
  chunk_count: number;
  error_message?: string | null;
  created_at: string;
  indexed_at?: string | null;
}

export interface IndexJob {
  id: string;
  document_id?: string | null;
  knowledge_base_id: string;
  celery_task_id?: string | null;
  kind: string;
  status: string;
  progress: number;
  message: string;
  error_message?: string | null;
}

export interface KnowledgeUploadResponse {
  document: KnowledgeDocument;
  job?: IndexJob | null;
  deduplicated: boolean;
}

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer" | string;
  user: AuthUser;
}

export interface ChatMessageRecord {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  events?: MonitorMessage[] | null;
  files?: OutputFile[] | null;
  created_at: string;
}

export interface ChatConversationRecord {
  id: string;
  thread_id: string;
  title: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  last_message_at: string;
}

export interface ChatConversationDetail extends ChatConversationRecord {
  messages: ChatMessageRecord[];
}
