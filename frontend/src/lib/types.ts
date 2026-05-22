/**
 * 共享类型定义（与后端 Pydantic Schema 对应）。
 */

export type Role = "user" | "assistant" | "system";

export type ChatMode = "chat" | "rag" | "agent";

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
