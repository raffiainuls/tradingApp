-- ═══════════════════════════════════════════════════════════════════════════
-- Trading Journal schema (Tab 1)
-- ═══════════════════════════════════════════════════════════════════════════

-- Posisi yang sedang dipegang (portofolio aktif)
CREATE TABLE IF NOT EXISTS positions (
    id            SERIAL PRIMARY KEY,
    symbol        VARCHAR(20)   NOT NULL,
    lots          INTEGER       NOT NULL CHECK (lots > 0),       -- 1 lot = 100 lembar
    avg_price     NUMERIC(14,2) NOT NULL CHECK (avg_price > 0),  -- harga beli rata-rata
    buy_date      DATE          NOT NULL,
    target_price  NUMERIC(14,2),                                 -- target jual
    cutloss_price NUMERIC(14,2),                                 -- batas cut loss
    sector        VARCHAR(50),
    reason        TEXT,                                          -- alasan beli
    tags          TEXT[],                                        -- breakout, dividen, dll
    notes         TEXT,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);

-- Log transaksi historis (beli/jual) → untuk realized P&L & analitik
CREATE TABLE IF NOT EXISTS transactions (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20)   NOT NULL,
    side        VARCHAR(4)    NOT NULL CHECK (side IN ('BUY', 'SELL')),
    trade_date  DATE          NOT NULL,
    price       NUMERIC(14,2) NOT NULL CHECK (price > 0),
    lots        INTEGER       NOT NULL CHECK (lots > 0),
    fee         NUMERIC(14,2) NOT NULL DEFAULT 0,                -- komisi broker
    sector      VARCHAR(50),
    tags        TEXT[],
    notes       TEXT,                                            -- catatan / kesalahan trading
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tx_symbol ON transactions(symbol);
CREATE INDEX IF NOT EXISTS idx_tx_date   ON transactions(trade_date);

-- Watchlist manual (Tab 3)
CREATE TABLE IF NOT EXISTS watchlist (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trigger: auto-update updated_at di positions
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_positions_touch ON positions;
CREATE TRIGGER trg_positions_touch
    BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ═══════════════════════════════════════════════════════════════════════════
-- Seed data contoh (boleh dihapus)
-- ═══════════════════════════════════════════════════════════════════════════
INSERT INTO positions (symbol, lots, avg_price, buy_date, target_price, cutloss_price, sector, reason, tags)
VALUES
    ('BBCA', 10, 9200,  '2026-05-12', 10500, 8800,  'Banking',  'Breakout MA200 dengan volume tinggi', ARRAY['breakout','bluechip']),
    ('TLKM', 20, 3650,  '2026-06-01', 4200,  3400,  'Telco',    'Oversold + dividen yield menarik',     ARRAY['dividen','turnaround']),
    ('ADRO', 15, 3100,  '2026-06-15', 3600,  2900,  'Energy',   'Momentum sektor batu bara',            ARRAY['momentum'])
ON CONFLICT DO NOTHING;

INSERT INTO transactions (symbol, side, trade_date, price, lots, fee, sector, tags, notes)
VALUES
    ('BBRI', 'BUY',  '2026-03-10', 5100, 20, 5000,  'Banking', ARRAY['swing'],   'Entry di support'),
    ('BBRI', 'SELL', '2026-04-02', 5600, 20, 5500,  'Banking', ARRAY['swing'],   'Take profit di resistance'),
    ('ANTM', 'BUY',  '2026-04-15', 1500, 30, 4500,  'Mining',  ARRAY['momentum'],'FOMO entry'),
    ('ANTM', 'SELL', '2026-04-22', 1380, 30, 4100,  'Mining',  ARRAY['momentum'],'Cut loss, salah timing'),
    ('GOTO', 'BUY',  '2026-05-05', 72,   100, 3600, 'Tech',    ARRAY['spekulasi'],'Spekulasi rebound'),
    ('GOTO', 'SELL', '2026-05-20', 88,   100, 4400, 'Tech',    ARRAY['spekulasi'],'Profit, sell on strength')
ON CONFLICT DO NOTHING;
