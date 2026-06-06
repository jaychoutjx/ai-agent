"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera,
  ImagePlus,
  RotateCcw,
  ScanText,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import { streamSolve } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SolveSubject } from "@/lib/types";

import "katex/dist/katex.min.css";

const SUBJECTS: { value: SolveSubject; label: string }[] = [
  { value: "auto", label: "自动判断" },
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
  { value: "biology", label: "生物" },
  { value: "english", label: "英语" },
  { value: "chinese", label: "语文" },
  { value: "history", label: "历史" },
  { value: "geography", label: "地理" },
  { value: "politics", label: "政治" },
  { value: "other", label: "其他" },
];

// 单张图片上限（base64 体积会比原图大约 1/3，这里限制原图 8MB）
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

export function SolvePanel() {
  const [imageData, setImageData] = useState<string | null>(null);
  const [subject, setSubject] = useState<SolveSubject>("auto");
  const [extra, setExtra] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const answerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    answerRef.current?.scrollTo({
      top: answerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [answer]);

  const loadFile = useCallback(async (file: File | null | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("请选择图片文件");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError("图片太大了，请压缩到 8MB 以内");
      return;
    }
    setError(null);
    try {
      const dataUrl = await readFileAsDataUrl(file);
      setImageData(dataUrl);
      setAnswer("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "图片读取失败");
    }
  }, []);

  // 支持从剪贴板直接粘贴截图
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) =>
        i.type.startsWith("image/"),
      );
      if (item) void loadFile(item.getAsFile());
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [loadFile]);

  const handleSolve = async () => {
    if (!imageData || loading) return;
    setAnswer("");
    setError(null);
    setLoading(true);
    abortRef.current = new AbortController();

    try {
      await streamSolve(
        {
          image_base64: imageData,
          subject,
          extra: extra.trim() || null,
          stream: true,
        },
        abortRef.current.signal,
        {
          onContent: (chunk) => setAnswer((p) => p + chunk),
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

  const handleStop = () => {
    abortRef.current?.abort();
    setLoading(false);
  };

  const handleReset = () => {
    abortRef.current?.abort();
    setImageData(null);
    setAnswer("");
    setError(null);
    setExtra("");
    setLoading(false);
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-sky-50/30">
      <div className="mx-auto w-full max-w-3xl px-3 py-5 sm:px-6 sm:py-6">
        {/* 上传区 */}
        <div className="mb-4 rounded-2xl border border-sky-100 bg-white p-4 sm:p-6">
          <h2 className="mb-1 flex items-center gap-2 text-lg font-bold text-gray-900">
            <ScanText size={20} className="text-sky-500" />
            拍照搜题
          </h2>
          <p className="mb-4 text-sm text-gray-500">
            拍照 / 上传 / 粘贴一张题目图片，AI 帮你识别题目、给出答案和解题步骤
          </p>

          {!imageData ? (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                void loadFile(e.dataTransfer.files?.[0]);
              }}
              className={cn(
                "flex w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-8 text-center transition",
                dragOver
                  ? "border-sky-400 bg-sky-50"
                  : "border-gray-300 bg-gray-50",
              )}
            >
              <ImagePlus size={32} className="text-sky-400" />
              <div className="flex flex-col gap-2 sm:flex-row">
                {/* 拍照：手机上唤起后置摄像头；桌面端无摄像头时退化为选图 */}
                <button
                  type="button"
                  onClick={() => cameraInputRef.current?.click()}
                  className="flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-sky-500 to-blue-500 px-5 py-2.5 text-sm font-medium text-white transition hover:shadow-md"
                >
                  <Camera size={16} />
                  拍照搜题
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center justify-center gap-1.5 rounded-xl border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 transition hover:border-sky-300 hover:text-sky-600"
                >
                  <ImagePlus size={16} />
                  从相册选择
                </button>
              </div>
              <span className="text-xs text-gray-400">
                <span className="hidden sm:inline">支持拖拽到此处，或 Ctrl/⌘+V 粘贴截图 · </span>
                单张 ≤ 8MB
              </span>
            </div>
          ) : (
            <div className="relative inline-block max-w-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageData}
                alt="题目预览"
                className="max-h-72 w-auto rounded-xl border border-gray-200 object-contain"
              />
              <button
                onClick={handleReset}
                className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-gray-800/80 text-white transition hover:bg-gray-900"
                title="移除图片"
              >
                <X size={15} />
              </button>
            </div>
          )}

          {/* 相册/文件选择 */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => void loadFile(e.target.files?.[0])}
          />
          {/* 拍照：capture 属性让移动端浏览器直接打开相机 */}
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => void loadFile(e.target.files?.[0])}
          />

          {/* 学科选择 */}
          <div className="mt-4">
            <label className="mb-2 block text-xs font-medium text-gray-600">
              学科
            </label>
            <div className="flex flex-wrap gap-1.5">
              {SUBJECTS.map((s) => (
                <button
                  key={s.value}
                  onClick={() => setSubject(s.value)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs transition",
                    subject === s.value
                      ? "border-sky-500 bg-sky-500 text-white"
                      : "border-gray-200 bg-white text-gray-600 hover:border-sky-300",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* 额外要求 */}
          <div className="mt-4">
            <label className="mb-2 block text-xs font-medium text-gray-600">
              额外要求（可选）
            </label>
            <input
              type="text"
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              placeholder="例如：只解第 2 题 / 用初中知识解答 / 解释为什么选 B"
              className="w-full rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5 text-sm outline-none transition focus:border-sky-500 focus:bg-white focus:ring-2 focus:ring-sky-500/20"
            />
          </div>

          {/* 操作按钮 */}
          <div className="mt-4 flex items-center gap-2">
            {loading ? (
              <button
                onClick={handleStop}
                className="flex items-center gap-2 rounded-xl bg-gray-700 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800"
              >
                <Square size={14} />
                停止
              </button>
            ) : (
              <button
                onClick={handleSolve}
                disabled={!imageData}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-500 px-5 py-2.5 text-sm font-medium text-white transition hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Sparkles size={16} />
                {answer ? "重新解题" : "开始解题"}
              </button>
            )}
            {imageData && (
              <button
                onClick={handleReset}
                className="flex items-center gap-1.5 rounded-xl px-3 py-2.5 text-sm text-gray-500 transition hover:bg-gray-100"
              >
                <RotateCcw size={14} />
                重置
              </button>
            )}
          </div>

          {error && (
            <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              ❌ {error}
            </p>
          )}
        </div>

        {/* 解题结果 */}
        {(answer || loading) && (
          <div
            ref={answerRef}
            className="max-h-[60vh] overflow-y-auto rounded-2xl border border-sky-100 bg-white p-4 sm:p-6"
          >
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-sky-600">
              <Sparkles size={14} />
              解题过程
            </div>
            {answer ? (
              <div className="prose prose-sm max-w-none break-words">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeKatex, rehypeHighlight]}
                >
                  {answer}
                </ReactMarkdown>
                {loading && (
                  <span className="ml-1 inline-block animate-pulse">▍</span>
                )}
              </div>
            ) : (
              <p className="flex items-center gap-2 text-sm text-gray-400">
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-500" />
                AI 正在识别题目并解答...
              </p>
            )}
          </div>
        )}

        <p className="mt-4 text-center text-[11px] text-gray-400">
          ⚠️ AI 解题结果仅供参考，请自行核对，尤其是计算题和证明题
        </p>
      </div>
    </div>
  );
}
