"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Citation } from "@/lib/types";

interface Props {
  citations: Citation[];
}

export function Citations({ citations }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (citations.length === 0) return null;

  return (
    <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 text-xs">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-gray-600 hover:bg-gray-100"
      >
        <span className="flex items-center gap-1.5">
          <FileText size={12} />
          引用 {citations.length} 个片段
        </span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && (
        <ol className="space-y-2 border-t border-gray-200 px-3 py-2">
          {citations.map((c, i) => (
            <li key={c.chunk_id || `${c.document_id}-${i}`} className="space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                    "bg-purple-100 text-purple-700",
                  )}
                >
                  {i + 1}
                </span>
                <span className="truncate font-medium text-gray-900">
                  {c.document_name}
                </span>
                <span className="ml-auto shrink-0 text-gray-500">
                  相关度 {c.score.toFixed(3)}
                </span>
              </div>
              <p className="line-clamp-3 pl-7 text-gray-600">{c.content}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
