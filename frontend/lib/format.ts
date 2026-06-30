// Formatting angka gaya Indonesia (titik ribuan, koma desimal) — TANPA Intl/toLocaleString.
// Catatan: toLocaleString("id-ID") bisa melempar RangeError "Incorrect locale information
// provided" di browser/runtime tanpa data ICU locale lengkap, yang dapat menggagalkan render.
// Implementasi manual ini aman di semua lingkungan.

function groupThousands(intStr: string): string {
  return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function fmtFixed(n: number, dec: number): string {
  const neg = n < 0;
  const fixed = Math.abs(n).toFixed(dec);
  const [int, frac] = fixed.split(".");
  let s = groupThousands(int);
  if (dec > 0 && frac) s += "," + frac;
  return (neg ? "-" : "") + s;
}

export const fmtNum = (n: number | null | undefined, dec = 0) =>
  n == null || isNaN(n) ? "–" : fmtFixed(n, dec);

export const fmtPrice = (n: number | null | undefined) => fmtNum(n, 0);

export const fmtPct = (n: number | null | undefined) =>
  n == null || isNaN(n) ? "–" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;

export const fmtVol = (v: number | null | undefined) => {
  if (v == null || isNaN(v)) return "–";
  if (v >= 1e12) return (v / 1e12).toFixed(2) + "T";
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toFixed(0);
};

export const fmtMoney = (n: number | null | undefined) => {
  if (n == null || isNaN(n)) return "–";
  const sign = n < 0 ? "-" : "";
  const a = Math.abs(n);
  if (a >= 1e9) return `${sign}Rp ${(a / 1e9).toFixed(2)} M`;
  if (a >= 1e6) return `${sign}Rp ${(a / 1e6).toFixed(1)} jt`;
  return `${sign}Rp ${fmtFixed(a, 0)}`;
};

export const colorOf = (n: number | null | undefined) =>
  n == null || n === 0 ? "text-dim" : n > 0 ? "text-up" : "text-down";
