/**
 * 知识库状态管理。
 *
 * 包括：
 * - 当前模式（普通对话 / 知识库问答）
 * - 文档列表
 * - 选中的文档（限定检索范围；空 = 全库检索）
 * - 上传/刷新逻辑
 */

import { create } from "zustand";
import {
  deleteDocument,
  listDocuments,
  uploadDocument,
} from "@/lib/api";
import type { ChatMode, DocumentMeta, RagSettings } from "@/lib/types";

interface KnowledgeState {
  mode: ChatMode;
  documents: DocumentMeta[];
  selectedDocIds: Set<string>;
  loading: boolean;
  ragSettings: RagSettings;

  setMode: (m: ChatMode) => void;
  refresh: () => Promise<void>;
  upload: (file: File) => Promise<DocumentMeta>;
  remove: (id: string) => Promise<void>;
  toggleSelect: (id: string) => void;
  clearSelected: () => void;
  updateRagSettings: (patch: Partial<RagSettings>) => void;
}

const DEFAULT_RAG_SETTINGS: RagSettings = {
  top_k: 5,
  use_bm25: true,
  use_rerank: true,
  use_multi_query: false,
  use_hyde: false,
};

export const useKnowledgeStore = create<KnowledgeState>((set) => ({
  mode: "chat",
  documents: [],
  selectedDocIds: new Set(),
  loading: false,
  ragSettings: DEFAULT_RAG_SETTINGS,

  setMode: (mode) => set({ mode }),

  updateRagSettings: (patch) =>
    set((s) => ({ ragSettings: { ...s.ragSettings, ...patch } })),

  refresh: async () => {
    set({ loading: true });
    try {
      const data = await listDocuments();
      set({ documents: data.documents });
    } finally {
      set({ loading: false });
    }
  },

  upload: async (file) => {
    const doc = await uploadDocument(file);
    set((s) => ({ documents: [doc, ...s.documents] }));
    return doc;
  },

  remove: async (id) => {
    await deleteDocument(id);
    set((s) => {
      const newSet = new Set(s.selectedDocIds);
      newSet.delete(id);
      return {
        documents: s.documents.filter((d) => d.id !== id),
        selectedDocIds: newSet,
      };
    });
  },

  toggleSelect: (id) =>
    set((s) => {
      const next = new Set(s.selectedDocIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { selectedDocIds: next };
    }),

  clearSelected: () => set({ selectedDocIds: new Set() }),
}));
