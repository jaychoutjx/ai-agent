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
