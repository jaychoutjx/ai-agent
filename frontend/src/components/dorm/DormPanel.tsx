"use client";

import { useEffect, useRef, useState } from "react";
import {
  Calendar,
  Filter,
  LogOut,
  MessageCircle,
  Sparkles,
  Theater,
  Users,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import {
  dormSummary,
  streamDormImitate,
  streamDormQuery,
} from "@/lib/api";
import { useDormStore } from "@/store/dorm";
import { useChatStore } from "@/store/chat";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { DormGate } from "./DormGate";
import { cn, stripCitationMarkers } from "@/lib/utils";
import type { ChatMessage, DormCitation } from "@/lib/types";

export function DormPanel() {
  const enabled = useDormStore((s) => s.enabled);
  const authenticated = useDormStore((s) => s.authenticated);
  const healthChecked = useDormStore((s) => s.healthChecked);
  const stats = useDormStore((s) => s.stats);
  const subMode = useDormStore((s) => s.subMode);
  const setSubMode = useDormStore((s) => s.setSubMode);
  const logout = useDormStore((s) => s.logout);

  // 健康检查未完成 → 显示 loading
  if (!healthChecked) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-400">
        正在加载...
      </div>
    );
  }
  // 后端没启用 → 不该出现在这里（外层会隐藏 tab），兜底提示
  if (!enabled) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-4 text-center text-gray-500">
        <h2 className="mb-2 text-lg font-semibold">🏠 寝室模式未开启</h2>
        <p className="text-sm">
          后端未配置 <code className="rounded bg-gray-100 px-1">DORM_ACCESS_TOKEN</code>
          ，此功能不可用
        </p>
      </div>
    );
  }
  // 已启用但未登录 → 显示口令遮罩
  if (!authenticated) {
    return <DormGate />;
  }

  return (
    <div className="flex h-full flex-col bg-rose-50/30">
      {/* 子模式切换 + 数据集信息 + 退出 */}
      <div className="flex flex-col gap-2 border-b border-rose-100 bg-white px-3 py-2 sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-3">
        <div className="flex items-center gap-2 overflow-x-auto">
          <SubModeButton
            active={subMode === "query"}
            onClick={() => setSubMode("query")}
            icon={<MessageCircle size={14} />}
            label="问答"
          />
          <SubModeButton
            active={subMode === "summary"}
            onClick={() => setSubMode("summary")}
            icon={<Sparkles size={14} />}
            label="周报"
          />
          <SubModeButton
            active={subMode === "imitate"}
            onClick={() => setSubMode("imitate")}
            icon={<Theater size={14} />}
            label="模仿"
          />
        </div>

        <div className="flex shrink-0 items-center gap-3 text-xs text-gray-500">
          {stats && (
            <span className="hidden sm:inline">
              📦 {stats.total_sessions} 块 · {stats.total_messages} 条消息
            </span>
          )}
          <button
            onClick={logout}
            className="flex items-center gap-1 rounded px-2 py-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            title="退出寝室模式"
          >
            <LogOut size={12} />
            <span>退出</span>
          </button>
        </div>
      </div>

      {/* 子模式内容区 */}
      <div className="flex-1 overflow-hidden">
        {subMode === "query" && <DormQuerySubMode />}
        {subMode === "summary" && <DormSummarySubMode />}
        {subMode === "imitate" && <DormImitateSubMode />}
      </div>
    </div>
  );
}

function SubModeButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex shrink-0 items-center gap-1 rounded-lg px-3 py-1.5 text-sm transition",
        active
          ? "bg-gradient-to-r from-pink-500 to-rose-500 text-white shadow-sm"
          : "bg-white text-gray-600 hover:bg-rose-50 hover:text-rose-600",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

// ============================================================
// 子模式 1: 问答
// ============================================================
function DormQuerySubMode() {
  const stats = useDormStore((s) => s.stats);
  const filterParticipants = useDormStore((s) => s.filterParticipants);
  const toggleFilterParticipant = useDormStore((s) => s.toggleFilterParticipant);
  const clearFilterParticipants = useDormStore((s) => s.clearFilterParticipants);
  const startDate = useDormStore((s) => s.startDate);
  const endDate = useDormStore((s) => s.endDate);
  const setDateRange = useDormStore((s) => s.setDateRange);

  const messages = useChatStore((s) => s.messages);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const addMessage = useChatStore((s) => s.addMessage);
  const appendToLastAssistant = useChatStore((s) => s.appendToLastAssistant);
  const finalizeLastAssistant = useChatStore((s) => s.finalizeLastAssistant);
  const setGenerating = useChatStore((s) => s.setGenerating);
  const setAbortController = useChatStore((s) => s.setAbortController);
  const abort = useChatStore((s) => s.abort);

  const [filterOpen, setFilterOpen] = useState(false);
  const [citations, setCitations] = useState<DormCitation[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const handleSend = async (text: string) => {
    setCitations([]);
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    };
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      streaming: true,
      createdAt: Date.now(),
    };
    addMessage(userMsg);
    addMessage(assistantMsg);

    const ac = new AbortController();
    setAbortController(ac);
    setGenerating(true);

    try {
      await streamDormQuery(
        {
          question: text,
          top_k: 8,
          start_date: startDate || null,
          end_date: endDate || null,
          participants: filterParticipants.length > 0 ? filterParticipants : null,
          stream: true,
        },
        ac.signal,
        {
          onCitations: (cs) => setCitations(cs),
          onContent: (chunk) => appendToLastAssistant(chunk),
          onDone: () => {
            finalizeLastAssistant();
            setGenerating(false);
            setAbortController(null);
          },
          onError: (err) => {
            appendToLastAssistant(`\n\n❌ 出错了：${err.message}`);
            finalizeLastAssistant();
            setGenerating(false);
            setAbortController(null);
          },
        },
      );
    } catch {
      // 已在 onError 处理
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* 筛选条 */}
      <div className="border-b border-rose-100 bg-white/50 px-3 py-2 sm:px-6">
        <button
          onClick={() => setFilterOpen((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-rose-600 hover:text-rose-700"
        >
          <Filter size={12} />
          筛选
          {(filterParticipants.length > 0 || startDate || endDate) && (
            <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px]">
              {filterParticipants.length + (startDate || endDate ? 1 : 0)}
            </span>
          )}
        </button>

        {filterOpen && (
          <div className="mt-2 flex flex-col gap-2 rounded-lg bg-white p-3 shadow-sm">
            {/* 时间筛选 */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Calendar size={12} className="text-gray-400" />
              <input
                type="date"
                value={startDate}
                onChange={(e) => setDateRange(e.target.value, endDate)}
                className="rounded border border-gray-200 px-2 py-1"
              />
              <span className="text-gray-400">~</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setDateRange(startDate, e.target.value)}
                className="rounded border border-gray-200 px-2 py-1"
              />
              {(startDate || endDate) && (
                <button
                  onClick={() => setDateRange("", "")}
                  className="text-gray-400 hover:text-gray-600"
                >
                  清除
                </button>
              )}
            </div>

            {/* 参与者筛选 */}
            {stats && stats.members.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <Users size={12} className="text-gray-400" />
                {stats.members.slice(0, 8).map((m) => {
                  const active = filterParticipants.includes(m.name);
                  return (
                    <button
                      key={m.name}
                      onClick={() => toggleFilterParticipant(m.name)}
                      className={cn(
                        "rounded-full px-2 py-0.5 transition",
                        active
                          ? "bg-rose-500 text-white"
                          : "bg-gray-100 text-gray-700 hover:bg-rose-100",
                      )}
                      title={`${m.message_count} 条`}
                    >
                      {m.name}
                    </button>
                  );
                })}
                {filterParticipants.length > 0 && (
                  <button
                    onClick={clearFilterParticipants}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    清除
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 消息列表 + 引用 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <DormQueryWelcome />
        ) : (
          <div className="mx-auto max-w-3xl px-1 sm:px-0">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {citations.length > 0 && <DormCitationsCard citations={citations} />}
          </div>
        )}
      </div>

      <ChatInput
        onSend={handleSend}
        onStop={abort}
        isGenerating={isGenerating}
      />
    </div>
  );
}

function DormQueryWelcome() {
  const stats = useDormStore((s) => s.stats);
  return (
    <div className="flex h-full flex-col items-center justify-center px-4 py-6 text-center">
      <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-pink-500 to-rose-400 text-white sm:h-16 sm:w-16">
        <MessageCircle size={28} />
      </div>
      <h2 className="mb-2 text-xl font-bold text-gray-900 sm:text-2xl">
        寝室记忆问答
      </h2>
      <p className="mb-6 px-2 text-sm text-gray-500 sm:text-base">
        问问群聊里发生过的事，AI 帮你翻聊天记录
        {stats && (
          <span className="mt-1 block text-xs text-gray-400">
            数据集：{stats.time_range.start?.slice(0, 10)} ~{" "}
            {stats.time_range.end?.slice(0, 10)} · {stats.members.length} 位成员
          </span>
        )}
      </p>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        {[
          "我们最近在群里聊过哪些有意思的事？",
          "群里聊过最多的人是谁？经常聊什么？",
          "我和高瑞祥有过哪些聊天的高光时刻？",
          "群里有没有提到过去吃饭、点外卖的记录？",
        ].map((s) => (
          <SuggestCard key={s} text={s} />
        ))}
      </div>
    </div>
  );
}

function SuggestCard({ text }: { text: string }) {
  // 把建议丢回输入框：用一个事件而不是直接调用 send（避免快速连发问题）
  return (
    <button
      onClick={() => {
        const ta = document.querySelector(
          "textarea[placeholder^='输入消息']",
        ) as HTMLTextAreaElement | null;
        if (ta) {
          ta.value = text;
          ta.focus();
          ta.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }}
      className="rounded-xl border border-rose-200 bg-white px-4 py-3 text-left text-sm text-gray-700 transition hover:border-rose-400 hover:shadow-sm"
    >
      {text}
    </button>
  );
}

function DormCitationsCard({ citations }: { citations: DormCitation[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mx-3 mb-4 sm:mx-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-rose-600 hover:text-rose-700"
      >
        📎 参考自 {citations.length} 段聊天 {open ? "▲ 收起" : "▼ 展开"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {citations.map((c) => (
            <div
              key={c.session_id}
              className="rounded-lg border border-rose-100 bg-white p-3 text-xs"
            >
              <div className="mb-1 flex items-center gap-2 text-gray-500">
                <span>🕐 {c.start_time}</span>
                <span>·</span>
                <span>👥 {c.participants.slice(0, 3).join("、")}</span>
                <span className="ml-auto text-rose-500">
                  相关度 {(c.score * 100).toFixed(0)}%
                </span>
              </div>
              <pre className="whitespace-pre-wrap break-words font-sans text-gray-700">
                {c.content.length > 400
                  ? c.content.slice(0, 400) + "..."
                  : c.content}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================
// 子模式 2: 周报
// ============================================================
function DormSummarySubMode() {
  const stats = useDormStore((s) => s.stats);
  const [range, setRange] = useState<"day" | "week" | "month" | "all">("week");
  const [report, setReport] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setReport("");
    try {
      const res = await dormSummary({
        range,
        end_date: stats?.time_range.end?.slice(0, 10) || null,
      });
      setReport(res.report);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-3 py-6 sm:px-6">
        <div className="mb-6 rounded-2xl border border-rose-100 bg-white p-4 sm:p-6">
          <h2 className="mb-1 text-lg font-bold text-gray-900">
            ✨ 群聊报告生成器
          </h2>
          <p className="mb-4 text-sm text-gray-500">
            自动总结指定时间段内的群聊：热点话题、金句趣事、发言情况
          </p>

          <div className="mb-4 flex flex-wrap gap-2">
            {[
              { value: "day", label: "近一天" },
              { value: "week", label: "近一周" },
              { value: "month", label: "近一月" },
              { value: "all", label: "全部" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() =>
                  setRange(opt.value as "day" | "week" | "month" | "all")
                }
                className={cn(
                  "rounded-full px-4 py-1.5 text-sm transition",
                  range === opt.value
                    ? "bg-gradient-to-r from-pink-500 to-rose-500 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-rose-100",
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-500 px-5 py-2.5 text-sm font-medium text-white transition hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <>
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                正在 Map-Reduce 总结中...
              </>
            ) : (
              <>
                <Sparkles size={16} />
                生成报告
              </>
            )}
          </button>
          {loading && (
            <p className="mt-2 text-xs text-gray-400">
              📊 拉取时间范围内的会话块 → 并发 Map 阶段总结 → Reduce 合成最终报告
              <br />
              数据多时大概要 30-60 秒...
            </p>
          )}
          {error && (
            <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              ❌ {error}
            </p>
          )}
        </div>

        {report && (
          <div className="rounded-2xl border border-rose-100 bg-white p-4 sm:p-6">
            <div className="prose prose-sm max-w-none break-words">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {stripCitationMarkers(report)}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// 子模式 3: 模仿
// ============================================================
function DormImitateSubMode() {
  const stats = useDormStore((s) => s.stats);
  const target = useDormStore((s) => s.imitateTarget);
  const setTarget = useDormStore((s) => s.setImitateTarget);

  const [input, setInput] = useState("");
  const [reply, setReply] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !target || loading) return;
    setReply("");
    setError(null);
    setLoading(true);
    abortRef.current = new AbortController();

    try {
      await streamDormImitate(
        { target_member: target, user_message: input.trim(), stream: true },
        abortRef.current.signal,
        {
          onContent: (chunk) => setReply((p) => p + chunk),
          onDone: () => setLoading(false),
          onError: (err) => {
            setError(err.message);
            setLoading(false);
          },
        },
      );
    } catch {
      // 已在 onError 处理
    }
  };

  const members = stats?.members ?? [];

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-2xl px-3 py-6 sm:px-6">
        <div className="mb-4 rounded-2xl border border-rose-100 bg-white p-4 sm:p-6">
          <h2 className="mb-1 text-lg font-bold text-gray-900">
            🎭 室友说话风格模仿
          </h2>
          <p className="mb-4 text-sm text-gray-500">
            选一位室友，AI 会基于 TA 在群里的真实发言来模仿语气回复你
          </p>

          {/* 室友选择 */}
          <div className="mb-4">
            <label className="mb-2 block text-xs font-medium text-gray-600">
              模仿对象
            </label>
            <div className="flex flex-wrap gap-2">
              {members.map((m) => (
                <button
                  key={m.name}
                  onClick={() => setTarget(m.name)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs transition",
                    target === m.name
                      ? "border-rose-500 bg-rose-500 text-white"
                      : "border-gray-200 bg-white text-gray-600 hover:border-rose-300",
                  )}
                >
                  {m.name}
                  <span
                    className={cn(
                      "ml-1.5 text-[10px]",
                      target === m.name ? "text-white/80" : "text-gray-400",
                    )}
                  >
                    {m.message_count}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <label className="block text-xs font-medium text-gray-600">
              对 TA 说点什么
            </label>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={3}
              placeholder={target ? `跟"${target}"说什么呢？` : "先选个室友"}
              className="w-full resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 text-sm outline-none transition focus:border-rose-500 focus:bg-white focus:ring-2 focus:ring-rose-500/20"
            />
            <button
              type="submit"
              disabled={!input.trim() || !target || loading}
              className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-500 px-5 py-2 text-sm font-medium text-white transition hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <>
                  <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  生成中...
                </>
              ) : (
                <>
                  <Theater size={14} />
                  模仿回复
                </>
              )}
            </button>
          </form>

          {error && (
            <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              ❌ {error}
            </p>
          )}
        </div>

        {(reply || loading) && (
          <div className="rounded-2xl border border-rose-100 bg-white p-4 sm:p-6">
            <div className="mb-2 text-xs font-medium text-rose-600">
              🎭 {target} 的「AI 替身」
            </div>
            <div className="text-base leading-relaxed text-gray-900">
              {reply}
              {loading && (
                <span className="ml-1 inline-block animate-pulse">▍</span>
              )}
            </div>
            <p className="mt-3 text-[11px] text-gray-400">
              ⚠️ AI 仅基于群聊语料模仿语言风格，不代表本人真实想法
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
