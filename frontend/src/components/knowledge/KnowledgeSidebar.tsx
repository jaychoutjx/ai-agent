"use client";

import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Check,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { getDocument } from "@/lib/api";
import { useKnowledgeStore } from "@/store/knowledge";
import { cn } from "@/lib/utils";
import type { DocumentMeta, DocumentStatus } from "@/lib/types";

const STATUS_LABEL: Record<DocumentStatus, string> = {
  pending: "等待处理",
  parsing: "解析中",
  chunking: "分块中",
  embedding: "向量化中",
  ready: "可用",
  failed: "失败",
};

const STATUS_COLOR: Record<DocumentStatus, string> = {
  pending: "bg-gray-100 text-gray-600",
  parsing: "bg-blue-100 text-blue-700",
  chunking: "bg-blue-100 text-blue-700",
  embedding: "bg-blue-100 text-blue-700",
  ready: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function KnowledgeSidebar({ onClose }: { onClose: () => void }) {
  const documents = useKnowledgeStore((s) => s.documents);
  const selectedDocIds = useKnowledgeStore((s) => s.selectedDocIds);
  const refresh = useKnowledgeStore((s) => s.refresh);
  const upload = useKnowledgeStore((s) => s.upload);
  const remove = useKnowledgeStore((s) => s.remove);
  const toggleSelect = useKnowledgeStore((s) => s.toggleSelect);
  const clearSelected = useKnowledgeStore((s) => s.clearSelected);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    refresh().catch(() => setError("无法连接后端"));
  }, [refresh]);

  // 轮询：如果有处于"非 ready/failed"状态的文档，每 2 秒刷新一次
  useEffect(() => {
    const pending = documents.some(
      (d) => d.status !== "ready" && d.status !== "failed",
    );
    if (!pending) return;

    const interval = setInterval(async () => {
      const updates = await Promise.all(
        documents
          .filter((d) => d.status !== "ready" && d.status !== "failed")
          .map((d) => getDocument(d.id).catch(() => null)),
      );
      if (updates.some((u) => u !== null)) {
        await refresh();
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [documents, refresh]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await upload(file);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (e: React.MouseEvent, doc: DocumentMeta) => {
    e.stopPropagation();
    if (!confirm(`确定要删除「${doc.filename}」吗？`)) return;
    try {
      await remove(doc.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  return (
    <aside className="flex h-full w-80 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <BookOpen className="text-purple-500" size={18} />
          <h2 className="text-sm font-semibold text-gray-900">知识库</h2>
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
            {documents.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => refresh()}
            className="rounded p-1.5 text-gray-500 transition hover:bg-gray-100"
            title="刷新"
          >
            <RefreshCw size={14} />
          </button>
          <button
            onClick={onClose}
            className="rounded p-1.5 text-gray-500 transition hover:bg-gray-100"
            title="关闭"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="border-b border-gray-200 p-3">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.md,.markdown,.txt,.xlsx"
          onChange={handleUpload}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className={cn(
            "flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed px-3 py-3 text-sm transition",
            "border-purple-300 bg-purple-50 text-purple-700 hover:border-purple-400 hover:bg-purple-100",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          {uploading ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              上传中...
            </>
          ) : (
            <>
              <Upload size={16} />
              上传文档
            </>
          )}
        </button>
        <p className="mt-2 text-center text-xs text-gray-400">
          支持 PDF / Word / Markdown / TXT / Excel
        </p>
        {error && (
          <p className="mt-2 rounded bg-red-50 p-2 text-xs text-red-700">
            {error}
          </p>
        )}
      </div>

      {selectedDocIds.size > 0 && (
        <div className="flex items-center justify-between border-b border-gray-200 bg-blue-50 px-4 py-2">
          <span className="text-xs text-blue-700">
            已选中 {selectedDocIds.size} 篇用于检索
          </span>
          <button
            onClick={clearSelected}
            className="text-xs text-blue-600 hover:underline"
          >
            清除
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {documents.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-sm text-gray-400">
            <FileText size={32} className="mb-2 opacity-50" />
            <p>暂无文档</p>
            <p className="text-xs">上传后即可基于文档问答</p>
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {documents.map((doc) => {
              const selected = selectedDocIds.has(doc.id);
              const isProcessing =
                doc.status !== "ready" && doc.status !== "failed";
              const canSelect = doc.status === "ready";
              return (
                <li
                  key={doc.id}
                  onClick={() => canSelect && toggleSelect(doc.id)}
                  className={cn(
                    "group flex items-start gap-2 px-4 py-3 transition",
                    canSelect && "cursor-pointer hover:bg-gray-50",
                    selected && "bg-blue-50 hover:bg-blue-100",
                  )}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border",
                      selected
                        ? "border-blue-500 bg-blue-500 text-white"
                        : "border-gray-300 bg-white",
                      !canSelect && "opacity-30",
                    )}
                  >
                    {selected && <Check size={12} />}
                  </div>

                  <div className="min-w-0 flex-1">
                    <p
                      className="truncate text-sm font-medium text-gray-900"
                      title={doc.filename}
                    >
                      {doc.filename}
                    </p>
                    <div className="mt-1 flex items-center gap-2 text-xs">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5",
                          STATUS_COLOR[doc.status],
                        )}
                      >
                        {isProcessing && (
                          <Loader2
                            size={10}
                            className="mr-1 inline animate-spin"
                          />
                        )}
                        {STATUS_LABEL[doc.status]}
                      </span>
                      <span className="text-gray-500">
                        {formatSize(doc.file_size)}
                      </span>
                      {doc.chunk_count > 0 && (
                        <span className="text-gray-500">
                          {doc.chunk_count} 块
                        </span>
                      )}
                    </div>
                    {doc.error_message && (
                      <p
                        className="mt-1 truncate text-xs text-red-500"
                        title={doc.error_message}
                      >
                        {doc.error_message}
                      </p>
                    )}
                  </div>

                  <button
                    onClick={(e) => handleDelete(e, doc)}
                    className="rounded p-1 text-gray-400 opacity-0 transition hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                    title="删除"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
