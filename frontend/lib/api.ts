import type {
  HistoryResponse, SymbolInfo, Quote, Position, PortfolioSummary,
  Allocation, Transaction, Analytics, ScreenerResult, WatchlistItem, ScreenerPreset,
} from "./types";

// Alamat backend diturunkan saat RUNTIME dari host yang dipakai membuka frontend
// (port 8000), bukan hard-code "localhost". Jadi tetap benar saat diakses lewat
// localhost, 127.0.0.1, maupun IP/hostname LAN. Hindari masalah "localhost:8000"
// menunjuk ke mesin yang salah ketika dashboard dibuka dari perangkat lain.
const BACKEND_PORT = 8000;

function apiBase(): string {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`;
  }
  return process.env.NEXT_PUBLIC_API_URL || `http://localhost:${BACKEND_PORT}`;
}

export function wsUrl(): string {
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.hostname}:${BACKEND_PORT}`;
  }
  return `ws://localhost:${BACKEND_PORT}`;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

// ── Market (Tab 2) ──
export const api = {
  symbols: () => get<{ stocks: SymbolInfo[]; indices: SymbolInfo[] }>("/api/symbols"),
  quotes: (interval = "1d") => get<Quote[]>(`/api/quotes?interval=${interval}`),
  history: (symbol: string, interval: string, indicators?: string) =>
    get<HistoryResponse>(
      `/api/history/${symbol}?interval=${interval}&limit=400` +
        (indicators ? `&indicators=${indicators}` : "")
    ),

  // ── Journal (Tab 1) ──
  positions: () =>
    get<{ positions: Position[]; summary: PortfolioSummary; allocation: Allocation[] }>(
      "/api/journal/positions"
    ),
  createPosition: (p: unknown) => send<Position>("POST", "/api/journal/positions", p),
  updatePosition: (id: number, p: unknown) => send<Position>("PUT", `/api/journal/positions/${id}`, p),
  deletePosition: (id: number) => send<void>("DELETE", `/api/journal/positions/${id}`),

  transactions: () => get<{ transactions: Transaction[] }>("/api/journal/transactions"),
  createTransaction: (t: unknown) => send<Transaction>("POST", "/api/journal/transactions", t),
  deleteTransaction: (id: number) => send<void>("DELETE", `/api/journal/transactions/${id}`),

  analytics: () => get<Analytics>("/api/journal/analytics"),

  // ── Watchlist + Screener (Tab 3) ──
  screener: (params: Record<string, string | number | boolean>) => {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== "" && v !== undefined && v !== null)
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join("&");
    return get<{ interval: string; count: number; results: ScreenerResult[] }>(`/api/screener?${qs}`);
  },
  screenerPresets: () => get<{ presets: ScreenerPreset[] }>("/api/screener/presets"),
  watchlist: () => get<{ watchlist: WatchlistItem[] }>("/api/watchlist"),
  addWatchlist: (body: { symbol: string; note?: string }) => send<WatchlistItem>("POST", "/api/watchlist", body),
  delWatchlist: (id: number) => send<void>("DELETE", `/api/watchlist/${id}`),
};
