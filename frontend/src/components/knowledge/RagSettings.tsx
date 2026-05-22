"use client";

import { useState } from "react";
import { Settings, X } from "lucide-react";
import { useKnowledgeStore } from "@/store/knowledge";
import { cn } from "@/lib/utils";

interface ToggleProps {
  label: string;
  desc: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  badge?: "推荐" | "性能开销" | "实验";
}

function Toggle({ label, desc, checked, onChange, badge }: ToggleProps) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg p-2 transition hover:bg-gray-50">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 cursor-pointer rounded border-gray-300 text-purple-600 focus:ring-purple-500"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-900">{label}</span>
          {badge && (
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px]",
                badge === "推荐" && "bg-green-100 text-green-700",
                badge === "性能开销" && "bg-amber-100 text-amber-700",
                badge === "实验" && "bg-purple-100 text-purple-700",
              )}
            >
              {badge}
            </span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-gray-500">{desc}</p>
      </div>
    </label>
  );
}

export function RagSettingsPanel() {
  const settings = useKnowledgeStore((s) => s.ragSettings);
  const update = useKnowledgeStore((s) => s.updateRagSettings);
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-gray-600 transition hover:bg-gray-100"
        title="检索设置"
      >
        <Settings size={16} />
        检索设置
      </button>

      {open && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/30"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
              <h3 className="font-semibold text-gray-900">RAG 检索设置</h3>
              <button
                onClick={() => setOpen(false)}
                className="rounded p-1 text-gray-500 hover:bg-gray-100"
              >
                <X size={18} />
              </button>
            </header>

            <div className="space-y-4 px-5 py-4">
              <div>
                <label className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-medium text-gray-900">召回数量 (Top-K)</span>
                  <span className="text-purple-700">{settings.top_k}</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={15}
                  step={1}
                  value={settings.top_k}
                  onChange={(e) => update({ top_k: Number(e.target.value) })}
                  className="w-full accent-purple-600"
                />
                <p className="text-xs text-gray-500">
                  返回多少个相关片段给大模型作为上下文
                </p>
              </div>

              <div className="space-y-1 border-t border-gray-100 pt-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  检索优化
                </p>
                <Toggle
                  label="混合检索 (BM25 + 向量)"
                  desc="结合关键词匹配，提升专有名词、代号场景的召回率"
                  checked={settings.use_bm25}
                  onChange={(v) => update({ use_bm25: v })}
                  badge="推荐"
                />
                <Toggle
                  label="Reranker 重排"
                  desc="用 Cross-Encoder 对粗排结果二次排序，MRR 通常 +5-10%"
                  checked={settings.use_rerank}
                  onChange={(v) => update({ use_rerank: v })}
                  badge="推荐"
                />
                <Toggle
                  label="Multi-Query 多查询改写"
                  desc="LLM 生成多个等价查询合并检索，覆盖表述差异"
                  checked={settings.use_multi_query}
                  onChange={(v) =>
                    update({
                      use_multi_query: v,
                      use_hyde: v ? false : settings.use_hyde,
                    })
                  }
                  badge="性能开销"
                />
                <Toggle
                  label="HyDE 假设文档嵌入"
                  desc="LLM 先幻想一个答案再检索（与 Multi-Query 二选一）"
                  checked={settings.use_hyde}
                  onChange={(v) =>
                    update({
                      use_hyde: v,
                      use_multi_query: v ? false : settings.use_multi_query,
                    })
                  }
                  badge="实验"
                />
              </div>
            </div>

            <footer className="flex justify-end gap-2 border-t border-gray-200 bg-gray-50 px-5 py-3">
              <button
                onClick={() =>
                  update({
                    top_k: 5,
                    use_bm25: true,
                    use_rerank: true,
                    use_multi_query: false,
                    use_hyde: false,
                  })
                }
                className="rounded-lg px-3 py-1.5 text-sm text-gray-600 transition hover:bg-gray-200"
              >
                恢复推荐
              </button>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg bg-purple-600 px-4 py-1.5 text-sm text-white transition hover:bg-purple-700"
              >
                完成
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
