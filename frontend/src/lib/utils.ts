import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * 合并 Tailwind 类名（shadcn/ui 标准工具函数）。
 * 用法: cn("px-2 py-1", isActive && "bg-blue-500", "px-4")
 *      会得到 "py-1 bg-blue-500 px-4"（自动去重并保留后写的）
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 清洗 LLM 回答中残留的引用编号。
 *
 * RAG/Agent 的回答里有时会出现 `[1]`、`[2,3]`、`【1】`、`(来源 1)` 这类标记，
 * 但我们已经在底部用「参考来源」卡片单独展示了引用，所以正文里这些标号是冗余的。
 *
 * 兜底策略：即使后端 prompt 已经要求 LLM 不要输出，也仍然在前端清洗一遍，
 * 避免某些模型不听话或缓存的旧回答有这种残留。
 *
 * 处理：
 *   - `[1]` `[2]` `[1, 2]`           → 去掉
 *   - `【1】` `【1，2】`              → 去掉
 *   - `(来源: 1)` `（来源 1，2）`    → 去掉
 *   - 但保留 markdown 链接 `[xxx](http://...)` 和代码块里的 `[1]`
 *
 * 注：为了不破坏代码块里的字符串，我们用一个简化策略——只清"纯数字"的中括号引用，
 *     代码里的 `arr[0]` 之类的不会被误删。
 */
export function stripCitationMarkers(text: string): string {
  if (!text) return text;
  return (
    text
      // 半角中括号：[1] [2,3] [1, 2 , 3]
      .replace(/\[\d+(?:\s*[,，]\s*\d+)*\]/g, "")
      // 全角中括号：【1】【1，2】
      .replace(/【\d+(?:\s*[,，]\s*\d+)*】/g, "")
      // (来源: 1) （来源 1）（参考 1, 2）等
      .replace(/[(（]\s*(?:来源|参考|引用)\s*[:：]?\s*\d+(?:\s*[,，]\s*\d+)*\s*[)）]/g, "")
      // 句末多余的成对空格（清洗后可能留下"...回答 。"）
      .replace(/[ \t]+([。，；,;!?！？])/g, "$1")
  );
}
