/**
 * 共享类型定义（与后端 Pydantic Schema 对应）。
 */

export type Role = "user" | "assistant" | "system";

export type ChatMode = "chat" | "rag" | "agent" | "dorm";

export interface AgentToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  result_summary?: string;
  status: "running" | "done";
}

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  /** 是否正在流式生成中 */
  streaming?: boolean;
  /** 引用的知识库片段（RAG 模式使用） */
  citations?: Citation[];
  /** 引用的寝室会话片段（dorm 模式使用） */
  dormCitations?: DormCitation[];
  /** Agent 的工具调用历史 */
  tool_calls?: AgentToolCall[];
  createdAt: number;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_name: string;
  content: string;
  score: number;
  chunk_index: number;
}

export interface ChatRequest {
  message: string;
  history: { role: Role; content: string }[];
  stream?: boolean;
  temperature?: number;
}

// ========== 文档管理 ==========
export type DocumentStatus =
  | "pending"
  | "parsing"
  | "chunking"
  | "embedding"
  | "ready"
  | "failed";

export interface DocumentMeta {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  status: DocumentStatus;
  error_message?: string | null;
  created_at: string;
}

export interface DocumentListResponse {
  total: number;
  documents: DocumentMeta[];
}

export interface RagQueryRequest {
  question: string;
  top_k?: number;
  document_ids?: string[] | null;
  history?: { role: Role; content: string }[];
  stream?: boolean;
  use_bm25?: boolean;
  use_rerank?: boolean;
  use_multi_query?: boolean;
  use_hyde?: boolean;
}

export interface RagSettings {
  top_k: number;
  use_bm25: boolean;
  use_rerank: boolean;
  use_multi_query: boolean;
  use_hyde: boolean;
}

export interface AgentRequest {
  question: string;
  history?: { role: Role; content: string }[];
  document_ids?: string[] | null;
  stream?: boolean;
}

// ========== 寝室群聊 RAG ==========

/** 寝室会话片段（检索命中的引用） */
export interface DormCitation {
  session_id: string;
  start_time: string;
  end_time: string;
  participants: string[];
  content: string;
  score: number;
}

export interface DormQueryRequest {
  question: string;
  top_k?: number;
  start_date?: string | null;
  end_date?: string | null;
  participants?: string[] | null;
  history?: { role: Role; content: string }[];
  stream?: boolean;
}

export interface DormSummaryRequest {
  range: "day" | "week" | "month" | "all";
  end_date?: string | null;
}

export interface DormImitateRequest {
  target_member: string;
  user_message: string;
  stream?: boolean;
}

export interface DormStats {
  total_sessions: number;
  total_messages: number;
  members: { name: string; message_count: number; avg_length: number }[];
  time_range: { start: string | null; end: string | null };
  indexed_at?: string | null;
}

export interface DormHealth {
  enabled: boolean;
  authenticated: boolean;
}
