"use client";

import { useState } from "react";
import {
  BookOpen,
  Calculator,
  ChevronDown,
  ChevronUp,
  Clock,
  Globe,
  Loader2,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentToolCall } from "@/lib/types";

const TOOL_META: Record<
  string,
  { icon: typeof BookOpen; label: string; color: string }
> = {
  search_knowledge_base: {
    icon: BookOpen,
    label: "检索知识库",
    color: "text-purple-600 bg-purple-50 border-purple-200",
  },
  web_search: {
    icon: Globe,
    label: "联网搜索",
    color: "text-blue-600 bg-blue-50 border-blue-200",
  },
  calculator: {
    icon: Calculator,
    label: "计算器",
    color: "text-green-600 bg-green-50 border-green-200",
  },
  get_current_time: {
    icon: Clock,
    label: "获取时间",
    color: "text-amber-600 bg-amber-50 border-amber-200",
  },
};

function ToolMeta({ name }: { name: string }) {
  const meta = TOOL_META[name] ?? {
    icon: Wrench,
    label: name,
    color: "text-gray-600 bg-gray-50 border-gray-200",
  };
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium",
        meta.color,
      )}
    >
      <Icon size={11} />
      {meta.label}
    </span>
  );
}

export function AgentTrace({ toolCalls }: { toolCalls: AgentToolCall[] }) {
  const [expanded, setExpanded] = useState(true);

  if (toolCalls.length === 0) return null;

  const running = toolCalls.some((tc) => tc.status === "running");

  return (
    <div className="mb-2 rounded-lg border border-gray-200 bg-gradient-to-br from-gray-50 to-purple-50 text-xs">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-gray-700 hover:bg-white/50"
      >
        <span className="flex items-center gap-2">
          {running ? (
            <Loader2 size={12} className="animate-spin text-purple-500" />
          ) : (
            <Wrench size={12} className="text-purple-500" />
          )}
          <span className="font-medium">
            {running ? "Agent 正在思考..." : "思考过程"}
          </span>
          <span className="text-gray-500">
            (调用 {toolCalls.length} 个工具)
          </span>
        </span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && (
        <ol className="space-y-2 border-t border-gray-200 px-3 py-2">
          {toolCalls.map((tc, i) => (
            <li key={tc.id} className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-100 text-[10px] font-semibold text-purple-700">
                  {i + 1}
                </span>
                <ToolMeta name={tc.tool_name} />
                {tc.status === "running" && (
                  <span className="inline-flex items-center gap-1 text-purple-600">
                    <Loader2 size={10} className="animate-spin" />
                    执行中
                  </span>
                )}
              </div>

              {/* 参数 */}
              {Object.keys(tc.arguments).length > 0 && (
                <div className="ml-7 rounded bg-gray-100 px-2 py-1 font-mono text-[11px] text-gray-700">
                  {Object.entries(tc.arguments).map(([k, v]) => (
                    <div key={k} className="truncate">
                      <span className="text-gray-500">{k}:</span>{" "}
                      <span className="text-gray-900">
                        {typeof v === "string" ? v : JSON.stringify(v)}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* 结果 */}
              {tc.result_summary && (
                <div className="ml-7 rounded bg-white px-2 py-1.5 text-[11px] text-gray-600 ring-1 ring-gray-200">
                  <span className="text-gray-400">↪ </span>
                  <span className="line-clamp-2">{tc.result_summary}</span>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
