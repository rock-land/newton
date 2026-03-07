import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  api,
  type HealthResponse,
  type SignalFullResponse,
  type RegimeResponse,
  type TradeResponse,
} from "@/lib/api";

/* ---------- Helpers ---------- */

const INSTRUMENTS = ["EUR_USD", "BTC_USD"];
const POLL_INTERVAL_MS = 10_000;

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}h ${m}m ${s}s`;
}

function formatAge(seconds: number | null): string {
  if (seconds === null) return "N/A";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function StatusBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <Badge className="bg-green-900 text-green-200 hover:bg-green-900">OK</Badge>
  ) : (
    <Badge variant="destructive">DOWN</Badge>
  );
}

function AgeBadge({ seconds }: { seconds: number | null }) {
  if (seconds === null) return <Badge variant="outline">N/A</Badge>;
  if (seconds < 7200)
    return <Badge className="bg-green-900 text-green-200 hover:bg-green-900">{formatAge(seconds)}</Badge>;
  if (seconds < 14400)
    return <Badge className="bg-yellow-900 text-yellow-200 hover:bg-yellow-900">{formatAge(seconds)}</Badge>;
  return <Badge variant="destructive">{formatAge(seconds)}</Badge>;
}

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    STRONG_BUY: "bg-green-900 text-green-200 hover:bg-green-900",
    BUY: "bg-emerald-900 text-emerald-200 hover:bg-emerald-900",
    SELL: "bg-red-900 text-red-200 hover:bg-red-900",
    STRONG_SELL: "bg-red-900 text-red-200 hover:bg-red-900",
    NEUTRAL: "bg-zinc-700 text-zinc-200 hover:bg-zinc-700",
  };
  return <Badge className={colors[action] ?? "bg-zinc-700 text-zinc-200"}>{action}</Badge>;
}

function RegimeBadge({ label }: { label: string }) {
  const colors: Record<string, string> = {
    LOW_VOL_TRENDING: "bg-blue-900 text-blue-200 hover:bg-blue-900",
    LOW_VOL_RANGING: "bg-cyan-900 text-cyan-200 hover:bg-cyan-900",
    HIGH_VOL_TRENDING: "bg-orange-900 text-orange-200 hover:bg-orange-900",
    HIGH_VOL_RANGING: "bg-amber-900 text-amber-200 hover:bg-amber-900",
    UNKNOWN: "bg-zinc-700 text-zinc-200 hover:bg-zinc-700",
  };
  const short = label.replace(/_/g, " ");
  return <Badge className={colors[label] ?? "bg-zinc-700 text-zinc-200"}>{short}</Badge>;
}

function ConfidenceBadge({ band }: { band: string }) {
  const colors: Record<string, string> = {
    HIGH: "bg-green-900 text-green-200 hover:bg-green-900",
    MEDIUM: "bg-yellow-900 text-yellow-200 hover:bg-yellow-900",
    LOW: "bg-red-900 text-red-200 hover:bg-red-900",
  };
  return <Badge className={colors[band] ?? "bg-zinc-700 text-zinc-200"}>{band}</Badge>;
}

/* ---------- State types ---------- */

interface InstrumentData {
  signal: SignalFullResponse | null;
  regime: RegimeResponse | null;
  signalError: string | null;
  regimeError: string | null;
}

/* ---------- Dashboard ---------- */

export function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [instruments, setInstruments] = useState<Record<string, InstrumentData>>({});
  const [trades, setTrades] = useState<TradeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [killSwitchBusy, setKillSwitchBusy] = useState(false);

  const fetchAll = useCallback(async () => {
    // Fetch health, signals, regimes, and recent trades in parallel
    const [healthResult, tradesResult, ...instrumentResults] = await Promise.allSettled([
      api.health(),
      api.trades({ limit: 10 }),
      ...INSTRUMENTS.flatMap((inst) => [api.signal(inst), api.regime(inst)]),
    ]);

    // Health
    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
      setHealthError(null);
    } else {
      setHealthError(
        healthResult.reason instanceof Error ? healthResult.reason.message : "Health fetch failed",
      );
    }

    // Trades
    if (tradesResult.status === "fulfilled") {
      setTrades(tradesResult.value.trades);
    }

    // Per-instrument data (pairs of [signal, regime])
    const instData: Record<string, InstrumentData> = {};
    INSTRUMENTS.forEach((inst, i) => {
      const sigResult = instrumentResults[i * 2];
      const regResult = instrumentResults[i * 2 + 1];
      instData[inst] = {
        signal: sigResult.status === "fulfilled" ? (sigResult.value as SignalFullResponse) : null,
        regime: regResult.status === "fulfilled" ? (regResult.value as RegimeResponse) : null,
        signalError:
          sigResult.status === "rejected"
            ? sigResult.reason instanceof Error
              ? sigResult.reason.message
              : "Signal fetch failed"
            : null,
        regimeError:
          regResult.status === "rejected"
            ? regResult.reason instanceof Error
              ? regResult.reason.message
              : "Regime fetch failed"
            : null,
      };
    });
    setInstruments(instData);

    setLastFetch(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  const handleKillSwitch = async () => {
    if (!health) return;
    setKillSwitchBusy(true);
    try {
      if (health.kill_switch_active) {
        await api.deactivateKillSwitch();
      } else {
        await api.activateKillSwitch("Dashboard manual activation");
      }
      await fetchAll();
    } catch {
      // Refresh to get current state even on error
      await fetchAll();
    } finally {
      setKillSwitchBusy(false);
    }
  };

  if (loading) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (healthError && !health) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">Dashboard</h1>
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive-foreground">{healthError}</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Is the API server running on port 8000?
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          {lastFetch && (
            <span className="text-xs text-muted-foreground">
              Last updated: {lastFetch.toLocaleTimeString()}
              {healthError && <span className="ml-2 text-destructive-foreground">(stale)</span>}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {health?.kill_switch_active && (
            <Badge variant="destructive" className="text-sm">KILL SWITCH ACTIVE</Badge>
          )}
          <Button
            variant={health?.kill_switch_active ? "outline" : "destructive"}
            size="sm"
            disabled={killSwitchBusy}
            onClick={handleKillSwitch}
          >
            {killSwitchBusy
              ? "..."
              : health?.kill_switch_active
                ? "Deactivate Kill Switch"
                : "Activate Kill Switch"}
          </Button>
        </div>
      </div>

      {/* Health Summary Cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              System
            </CardTitle>
          </CardHeader>
          <CardContent>
            <StatusBadge ok={health?.status === "healthy"} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Database
            </CardTitle>
          </CardHeader>
          <CardContent>
            <StatusBadge ok={health?.db ?? false} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Uptime
            </CardTitle>
          </CardHeader>
          <CardContent>
            <span className="text-lg font-semibold">
              {health ? formatUptime(health.uptime_seconds) : "-"}
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Kill Switch
            </CardTitle>
          </CardHeader>
          <CardContent>
            {health?.kill_switch_active ? (
              <Badge variant="destructive">ACTIVE</Badge>
            ) : (
              <Badge className="bg-green-900 text-green-200 hover:bg-green-900">OFF</Badge>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Instrument Status Cards */}
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        {INSTRUMENTS.map((inst) => {
          const data = instruments[inst];
          const instHealth = health?.instruments?.[inst];
          const brokerName = inst === "EUR_USD" ? "oanda" : "binance";
          const broker = health?.brokers?.[brokerName];
          return (
            <Card key={inst}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="font-mono text-lg">{inst.replace("_", "/")}</CardTitle>
                  <StatusBadge ok={broker?.connected ?? false} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {/* Signal */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Signal</span>
                    {data?.signal ? (
                      <div className="flex items-center gap-2">
                        <ActionBadge action={data.signal.action} />
                        <span className="font-mono text-sm">
                          {(data.signal.probability * 100).toFixed(1)}%
                        </span>
                      </div>
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        {data?.signalError ?? "N/A"}
                      </span>
                    )}
                  </div>

                  {/* Regime */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Regime</span>
                    {data?.regime ? (
                      <div className="flex items-center gap-2">
                        <RegimeBadge label={data.regime.regime_label} />
                        <ConfidenceBadge band={data.regime.confidence_band} />
                      </div>
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        {data?.regimeError ?? "N/A"}
                      </span>
                    )}
                  </div>

                  {/* Data Freshness */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Last Candle</span>
                    <AgeBadge seconds={instHealth?.last_candle_age_seconds ?? null} />
                  </div>

                  {/* Broker */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Broker</span>
                    <span className="text-sm capitalize">{brokerName}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Portfolio Equity Placeholder */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Portfolio Equity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-32 items-center justify-center rounded-md border border-dashed border-muted-foreground/25">
            <p className="text-sm text-muted-foreground">
              Available in Stage 8 (Paper Trading)
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Recent Trades */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Trades</CardTitle>
        </CardHeader>
        <CardContent>
          {trades.length === 0 ? (
            <p className="text-sm text-muted-foreground">No trades recorded yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Instrument</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Entry Price</TableHead>
                  <TableHead>P&L</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.map((t) => (
                  <TableRow key={t.client_order_id}>
                    <TableCell className="font-mono">
                      {t.instrument.replace("_", "/")}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={
                          t.direction === "BUY"
                            ? "bg-green-900 text-green-200 hover:bg-green-900"
                            : "bg-red-900 text-red-200 hover:bg-red-900"
                        }
                      >
                        {t.direction}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{t.status}</Badge>
                    </TableCell>
                    <TableCell className="font-mono">
                      {t.entry_price?.toFixed(t.instrument === "BTC_USD" ? 2 : 5) ?? "-"}
                    </TableCell>
                    <TableCell
                      className={`font-mono ${
                        t.pnl !== null && t.pnl >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {t.pnl !== null ? `$${t.pnl.toFixed(2)}` : "-"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {t.created_at
                        ? new Date(t.created_at).toLocaleString()
                        : "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
