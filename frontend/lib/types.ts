export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LinePoint { time: number; value: number; }

export interface BandData { upper: LinePoint[]; middle: LinePoint[]; lower: LinePoint[]; }
export interface MacdData { macd: LinePoint[]; signal: LinePoint[]; hist: LinePoint[]; }
export interface StochData { k: LinePoint[]; d: LinePoint[]; }
export interface AdxData { adx: LinePoint[]; plus_di: LinePoint[]; minus_di: LinePoint[]; }
export interface VolProfile { levels: { price: number; volume: number }[]; poc: number | null; }

export interface Indicators {
  sma20?: LinePoint[]; sma50?: LinePoint[]; sma200?: LinePoint[];
  ema20?: LinePoint[]; ema50?: LinePoint[];
  bbands?: BandData; keltner?: BandData;
  vwap?: LinePoint[]; sar?: LinePoint[];
  macd?: MacdData; rsi?: LinePoint[]; stoch?: StochData;
  williams?: LinePoint[]; cci?: LinePoint[]; adx?: AdxData;
  atr?: LinePoint[]; obv?: LinePoint[]; ad?: LinePoint[];
  volprofile?: VolProfile;
}

export interface Signals {
  close?: number; rsi?: number; macd_hist?: number;
  adx?: number; plus_di?: number; minus_di?: number;
  sma20?: number; sma50?: number; sma200?: number;
  bb_upper?: number; bb_lower?: number; atr?: number;
  score?: number; verdict?: string;
}

export interface HistoryResponse {
  symbol: string;
  interval: string;
  candles: Candle[];
  indicators: Indicators;
  signals: Signals;
}

export interface SymbolInfo { symbol: string; sector: string | null; type: string; has_data: boolean; }
export interface Quote {
  symbol: string; sector: string | null; type: string;
  price: number; change: number; change_pct: number; volume: number;
}

// ── Journal ──
export interface Position {
  id: number; symbol: string; lots: number; avg_price: number;
  buy_date: string; target_price: number | null; cutloss_price: number | null;
  sector: string | null; reason: string | null; tags: string[] | null; notes: string | null;
  current_price: number; cost_basis: number; market_value: number;
  unrealized_pnl: number; return_pct: number;
}
export interface PortfolioSummary {
  total_cost: number; total_value: number; total_pnl: number;
  total_return_pct: number; position_count: number;
}
export interface Allocation { sector: string; value: number; pct: number; }
export interface Transaction {
  id: number; symbol: string; side: "BUY" | "SELL"; trade_date: string;
  price: number; lots: number; fee: number; sector: string | null;
  tags: string[] | null; notes: string | null;
}
export interface ClosedTrade {
  symbol: string; sector: string | null; buy_date: string; sell_date: string;
  buy_price: number; sell_price: number; lots: number; pnl: number;
  return_pct: number; holding_days: number;
}
export interface ScreenerResult {
  symbol: string; score: number; verdict: string; close: number; change_pct: number;
  rsi: number | null; macd_hist: number | null; adx: number | null;
  sma20: number | null; sma50: number | null; sma200: number | null;
  above_ma20: boolean; above_ma50: boolean; above_ma200: boolean;
  dist_ma200_pct: number | null; vol_ratio: number; volume: number; atr: number | null;
  board: string | null; name: string | null;
}
export interface WatchlistItem {
  id: number; symbol: string; note: string | null; created_at: string;
  price: number | null; change_pct: number | null; score: number | null;
  verdict: string | null; rsi: number | null;
}
export interface ScreenerPreset { key: string; label: string; params: Record<string, any>; }

export interface Analytics {
  stats: {
    total_realized_pnl: number; total_trades: number; wins: number; losses: number;
    win_rate: number; avg_win: number; avg_loss: number; profit_factor: number | null;
    avg_holding_days: number; best_trade: ClosedTrade | null; worst_trade: ClosedTrade | null;
  };
  per_symbol: { symbol: string; pnl: number; trades: number; win_rate: number }[];
  equity_curve: { date: string; equity: number }[];
  closed_trades: ClosedTrade[];
}
