/**
 * 寝室群聊模式状态管理。
 *
 * 关注点：
 * - 是否启用（后端有没有配 DORM_ACCESS_TOKEN）
 * - 当前是否已通过口令验证
 * - 数据集统计（成员、时间范围等）
 * - 子模式：query / summary / imitate
 * - 模仿对象、时间筛选、参与者筛选
 */

import { create } from "zustand";
import { dormHealthCheck, dormStats, getDormToken, setDormToken } from "@/lib/api";
import type { DormStats } from "@/lib/types";

export type DormSubMode = "query" | "summary" | "imitate";

interface DormState {
  /** 后端是否启用了 dorm 模式（DORM_ACCESS_TOKEN 是否配置） */
  enabled: boolean;
  /** 是否已通过口令验证 */
  authenticated: boolean;
  /** 健康检查是否完成（避免初始化时一直显示"加载中"） */
  healthChecked: boolean;
  /** 数据集统计 */
  stats: DormStats | null;

  /** 子模式 */
  subMode: DormSubMode;
  /** 模仿对象（仅 imitate 子模式用） */
  imitateTarget: string;
  /** 参与者过滤（query 子模式用） */
  filterParticipants: string[];
  /** 起始日期（query 子模式用） */
  startDate: string;
  /** 结束日期（query 子模式用） */
  endDate: string;

  bootstrap: () => Promise<void>;
  authenticate: (token: string) => Promise<boolean>;
  logout: () => void;
  refreshStats: () => Promise<void>;

  setSubMode: (m: DormSubMode) => void;
  setImitateTarget: (n: string) => void;
  toggleFilterParticipant: (name: string) => void;
  clearFilterParticipants: () => void;
  setDateRange: (start: string, end: string) => void;
}

export const useDormStore = create<DormState>((set, get) => ({
  enabled: false,
  authenticated: false,
  healthChecked: false,
  stats: null,

  subMode: "query",
  imitateTarget: "",
  filterParticipants: [],
  startDate: "",
  endDate: "",

  /**
   * 启动时调用：探测后端是否启用 + 用 sessionStorage 里的 token 试一下。
   */
  bootstrap: async () => {
    const health = await dormHealthCheck();
    set({
      enabled: health.enabled,
      authenticated: health.authenticated,
      healthChecked: true,
    });
    if (health.authenticated) {
      try {
        const stats = await dormStats();
        set({ stats });
        // 默认模仿对象选发言最多的人
        if (stats.members.length > 0 && !get().imitateTarget) {
          set({ imitateTarget: stats.members[0].name });
        }
      } catch (e) {
        console.error("[dorm] stats failed:", e);
      }
    }
  },

  authenticate: async (token) => {
    setDormToken(token);
    const health = await dormHealthCheck();
    if (health.authenticated) {
      set({ authenticated: true });
      try {
        const stats = await dormStats();
        set({ stats });
        if (stats.members.length > 0 && !get().imitateTarget) {
          set({ imitateTarget: stats.members[0].name });
        }
      } catch (e) {
        console.error("[dorm] stats failed:", e);
      }
      return true;
    }
    setDormToken("");
    return false;
  },

  logout: () => {
    setDormToken("");
    set({
      authenticated: false,
      stats: null,
      filterParticipants: [],
      startDate: "",
      endDate: "",
    });
  },

  refreshStats: async () => {
    if (!getDormToken()) return;
    try {
      const stats = await dormStats();
      set({ stats });
    } catch (e) {
      console.error("[dorm] refreshStats failed:", e);
    }
  },

  setSubMode: (m) => set({ subMode: m }),
  setImitateTarget: (n) => set({ imitateTarget: n }),

  toggleFilterParticipant: (name) =>
    set((s) => {
      const has = s.filterParticipants.includes(name);
      return {
        filterParticipants: has
          ? s.filterParticipants.filter((p) => p !== name)
          : [...s.filterParticipants, name],
      };
    }),

  clearFilterParticipants: () => set({ filterParticipants: [] }),

  setDateRange: (start, end) => set({ startDate: start, endDate: end }),
}));
