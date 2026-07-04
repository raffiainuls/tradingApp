export default function VerdictBadge({ v }: { v: string }) {
  const map: Record<string, string> = {
    "STRONG BUY": "text-up border-up bg-up/10", "BUY": "text-up border-up/50 bg-up/5",
    "NEUTRAL": "text-dim border-border", "SELL": "text-down border-down/50 bg-down/5",
    "STRONG SELL": "text-down border-down bg-down/10",
  };
  return <span className={`chip border ${map[v] || "text-dim border-border"}`}>{v}</span>;
}
