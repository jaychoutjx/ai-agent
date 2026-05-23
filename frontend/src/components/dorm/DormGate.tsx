"use client";

import { useState } from "react";
import { Lock, Loader2 } from "lucide-react";
import { useDormStore } from "@/store/dorm";

/**
 * 寝室模式的口令输入遮罩。
 * 后端启用了 DORM_ACCESS_TOKEN 但前端 token 还没通过验证时显示。
 */
export function DormGate() {
  const authenticate = useDormStore((s) => s.authenticate);
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const ok = await authenticate(token.trim());
      if (!ok) {
        setError("口令错误，请再试一次");
        setToken("");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "网络错误");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-full flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-md rounded-2xl border border-pink-100 bg-white p-6 shadow-sm sm:p-8">
        <div className="mb-4 flex items-center justify-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-pink-500 to-rose-400 text-white">
            <Lock size={26} />
          </div>
        </div>
        <h2 className="mb-1 text-center text-xl font-bold text-gray-900">
          🏠 寝室记忆助手
        </h2>
        <p className="mb-6 text-center text-sm text-gray-500">
          基于我们寝室群聊天记录的私人 RAG 助手
          <br />
          需要口令才能进入
        </p>

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="访问口令"
            autoFocus
            className="w-full rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 text-sm outline-none transition focus:border-pink-500 focus:bg-white focus:ring-2 focus:ring-pink-500/20"
          />
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={!token.trim() || submitting}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-500 px-4 py-3 text-sm font-medium text-white transition hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                验证中...
              </>
            ) : (
              "进入"
            )}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-gray-400">
          这个模式只对作者本人开放，里面包含私人聊天记录
        </p>
      </div>
    </div>
  );
}
