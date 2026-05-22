/**
 * 后端 API 客户端封装。
 *
 * 重点函数：streamChat
 *   使用 @microsoft/fetch-event-source 实现 SSE 流式调用。
 *
 * 为什么不用浏览器原生 EventSource？
 * 1. EventSource 只能 GET，不能 POST（我们要传 body）
 * 2. EventSource 不支持自定义 header（鉴权不方便）
 * 3. fetch-event-source 是 Microsoft 出的，社区标杆
 */

import { fetchEventSource } from "@microsoft/fetch-event-source";
import { config } from "./config";
import type {
  AgentRequest,
  ChatRequest,
  Citation,
  DocumentListResponse,
  DocumentMeta,
  RagQueryRequest,
} from "./types";

class FatalError extends Error {}
class RetriableError extends Error {}

interface StreamCallbacks {
  onContent: (chunk: string) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}

interface RagStreamCallbacks extends StreamCallbacks {
  onCitations: (citations: Citation[]) => void;
}

interface AgentStreamCallbacks extends StreamCallbacks {
  onStep?: (node: string) => void;
  onToolCall: (
    tool_name: string,
    arguments_: Record<string, unknown>,
  ) => void;
  onToolResult: (tool_name: string, summary: string) => void;
  onCitations: (citations: Citation[]) => void;
}

/**
 * SSE 流式聊天。
 *
 * @param req      聊天请求体
 * @param signal   AbortSignal，用于用户点"停止生成"
 * @param cb       回调函数
 */
export async function streamChat(
  req: ChatRequest,
  signal: AbortSignal,
  cb: StreamCallbacks,
): Promise<void> {
  const url = `${config.apiBaseUrl}/api/v1/chat/completions/stream`;

  await fetchEventSource(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(req),
    signal,
    openWhenHidden: true,

    async onopen(res) {
      if (res.ok && res.headers.get("content-type")?.includes("text/event-stream")) {
        return;
      }
      if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        throw new FatalError(`HTTP ${res.status}: ${res.statusText}`);
      }
      throw new RetriableError(`HTTP ${res.status}`);
    },

    onmessage(ev) {
      if (ev.data === "[DONE]") {
        cb.onDone();
        return;
      }
      try {
        const payload = JSON.parse(ev.data) as { content?: string; error?: string };
        if (payload.error) {
          cb.onError(new Error(payload.error));
          return;
        }
        if (payload.content) {
          cb.onContent(payload.content);
        }
      } catch {
        // 容错：忽略无法解析的 chunk
      }
    },

    onerror(err) {
      if (err instanceof FatalError) {
        cb.onError(err);
        throw err;
      }
      cb.onError(err);
      throw err;
    },

    onclose() {
      cb.onDone();
    },
  });
}

/**
 * 健康检查。用于前端启动时探测后端是否可用。
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${config.apiBaseUrl}/api/v1/health`, {
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ============================================================
// 文档管理 API
// ============================================================

export async function uploadDocument(file: File): Promise<DocumentMeta> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${config.apiBaseUrl}/api/v1/documents/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "上传失败");
  }
  const data = await res.json();
  return data.document as DocumentMeta;
}

export async function listDocuments(): Promise<DocumentListResponse> {
  const res = await fetch(`${config.apiBaseUrl}/api/v1/documents`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("获取文档列表失败");
  return res.json();
}

export async function getDocument(id: string): Promise<DocumentMeta> {
  const res = await fetch(`${config.apiBaseUrl}/api/v1/documents/${id}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("文档不存在");
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${config.apiBaseUrl}/api/v1/documents/${id}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) throw new Error("删除失败");
}

// ============================================================
// RAG 流式问答
// ============================================================

/**
 * RAG 流式问答。
 *
 * SSE 事件序列：
 *   data: {"type":"citations","citations":[...]}   # 先推引用
 *   data: {"type":"content","content":"..."}        # 然后流式推回答
 *   data: [DONE]
 */
export async function streamRag(
  req: RagQueryRequest,
  signal: AbortSignal,
  cb: RagStreamCallbacks,
): Promise<void> {
  const url = `${config.apiBaseUrl}/api/v1/rag/query/stream`;

  await fetchEventSource(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(req),
    signal,
    openWhenHidden: true,

    async onopen(res) {
      if (res.ok && res.headers.get("content-type")?.includes("text/event-stream")) {
        return;
      }
      if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        throw new FatalError(`HTTP ${res.status}: ${res.statusText}`);
      }
      throw new RetriableError(`HTTP ${res.status}`);
    },

    onmessage(ev) {
      if (ev.data === "[DONE]") {
        cb.onDone();
        return;
      }
      try {
        const payload = JSON.parse(ev.data);
        if (payload.type === "citations") {
          cb.onCitations(payload.citations ?? []);
        } else if (payload.type === "content") {
          cb.onContent(payload.content ?? "");
        } else if (payload.type === "error") {
          cb.onError(new Error(payload.error ?? "Unknown error"));
        }
      } catch {
        // 容错
      }
    },

    onerror(err) {
      if (err instanceof FatalError) {
        cb.onError(err);
        throw err;
      }
      cb.onError(err);
      throw err;
    },

    onclose() {
      cb.onDone();
    },
  });
}

// ============================================================
// Agent 流式问答（节点进度 + 工具调用 + 内容）
// ============================================================
export async function streamAgent(
  req: AgentRequest,
  signal: AbortSignal,
  cb: AgentStreamCallbacks,
): Promise<void> {
  const url = `${config.apiBaseUrl}/api/v1/agent/run/stream`;

  await fetchEventSource(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(req),
    signal,
    openWhenHidden: true,

    async onopen(res) {
      if (
        res.ok &&
        res.headers.get("content-type")?.includes("text/event-stream")
      ) {
        return;
      }
      if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        throw new FatalError(`HTTP ${res.status}: ${res.statusText}`);
      }
      throw new RetriableError(`HTTP ${res.status}`);
    },

    onmessage(ev) {
      if (ev.data === "[DONE]") {
        cb.onDone();
        return;
      }
      try {
        const payload = JSON.parse(ev.data);
        switch (payload.type) {
          case "step":
            cb.onStep?.(payload.node ?? "");
            break;
          case "tool_call":
            cb.onToolCall(payload.tool_name ?? "", payload.arguments ?? {});
            break;
          case "tool_result":
            cb.onToolResult(payload.tool_name ?? "", payload.summary ?? "");
            break;
          case "content":
            cb.onContent(payload.content ?? "");
            break;
          case "citations":
            cb.onCitations(payload.citations ?? []);
            break;
          case "error":
            cb.onError(new Error(payload.error ?? "Unknown error"));
            break;
        }
      } catch {
        // 容错
      }
    },

    onerror(err) {
      if (err instanceof FatalError) {
        cb.onError(err);
        throw err;
      }
      cb.onError(err);
      throw err;
    },

    onclose() {
      cb.onDone();
    },
  });
}
