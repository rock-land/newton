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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import {
  api,
  type TradeResponse,
  type CircuitBreakersResponse,
  type CircuitBreakerState,
  type ReconciliationResponse,
  type SignalFullResponse,
} from "@/lib/api";

/* ---------- Constants ---------- */

const INSTRUMENTS = ["EUR_USD", "BTC_USD"];
const POLL_INTERVAL_MS = 10_000;

/* ---------- Badge helpers ---------- */

function StatusBadge({ tripped }: { tripped: boolean }) {
  return tripped ? (
    <Badge variant="destructive">TRIPPED</Badge>
  ) : (
    <Badge className="bg-green-900 text-green-200 hover:bg-green-900">OK</Badge>
  );
}

function DirectionBadge({ direction }: { direction: string }) {
  return (
    <Badge
      className={
        direction === "BUY"
          ? "bg-green-900 text-green-200 hover:bg-green-900"
          : "bg-red-900 text-red-200 hover:bg-red-900"
      }
    >
      {direction}
    </Badge>
  );
}

function TradeStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    OPEN: "bg-blue-900 text-blue-200 hover:bg-blue-900",
    CLOSED: "bg-zinc-700 text-zinc-200 hover:bg-zinc-700",
    PENDING: "bg-yellow-900 text-yellow-200 hover:bg-yellow-900",
    CANCELLED: "bg-zinc-600 text-zinc-300 hover:bg-zinc-600",
    REJECTED: "bg-red-900 text-red-200 hover:bg-red-900",
  };
  return <Badge className={colors[status] ?? "bg-zinc-700 text-zinc-200"}>{status}</Badge>;
}

function ReconStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    MATCH: "bg-green-900 text-green-200 hover:bg-green-900",
    SYSTEM_EXTRA: "bg-red-900 text-red-200 hover:bg-red-900",
    BROKER_EXTRA: "bg-orange-900 text-orange-200 hover:bg-orange-900",
  };
  return <Badge className={colors[status] ?? "bg-zinc-700 text-zinc-200"}>{status}</Badge>;
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

/* ---------- Open Positions Tab ---------- */

function OpenPositionsTab({
  trades,
  onClose,
  closingId,
}: {
  trades: TradeResponse[];
  onClose: (orderId: string) => void;
  closingId: string | null;
}) {
  const openTrades = trades.filter((t) => t.status === "OPEN");

  if (openTrades.length === 0) {
    return <p className="text-sm text-muted-foreground">No open positions.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Instrument</TableHead>
          <TableHead>Direction</TableHead>
          <TableHead>Entry Price</TableHead>
          <TableHead>Quantity</TableHead>
          <TableHead>Stop Loss</TableHead>
          <TableHead>P&L</TableHead>
          <TableHead>Opened</TableHead>
          <TableHead></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {openTrades.map((t) => (
          <TableRow key={t.client_order_id}>
            <TableCell className="font-mono">{t.instrument.replace("_", "/")}</TableCell>
            <TableCell><DirectionBadge direction={t.direction} /></TableCell>
            <TableCell className="font-mono">
              {t.entry_price?.toFixed(t.instrument === "BTC_USD" ? 2 : 5) ?? "-"}
            </TableCell>
            <TableCell className="font-mono">{t.quantity}</TableCell>
            <TableCell className="font-mono">
              {t.stop_loss_price?.toFixed(t.instrument === "BTC_USD" ? 2 : 5) ?? "-"}
            </TableCell>
            <TableCell
              className={`font-mono ${
                t.pnl !== null && t.pnl >= 0 ? "text-green-400" : "text-red-400"
              }`}
            >
              {t.pnl !== null ? `$${t.pnl.toFixed(2)}` : "-"}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {t.entry_time ? new Date(t.entry_time).toLocaleString() : "-"}
            </TableCell>
            <TableCell>
              <Button
                variant="destructive"
                size="sm"
                disabled={closingId === t.client_order_id}
                onClick={() => onClose(t.client_order_id)}
              >
                {closingId === t.client_order_id ? "..." : "Close"}
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/* ---------- Trade History Tab ---------- */

function TradeHistoryTab({ trades }: { trades: TradeResponse[] }) {
  const [filterInstrument, setFilterInstrument] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  const filtered = trades.filter((t) => {
    if (filterInstrument && !t.instrument.toLowerCase().includes(filterInstrument.toLowerCase()))
      return false;
    if (filterStatus && t.status !== filterStatus.toUpperCase()) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <Input
          placeholder="Filter instrument..."
          value={filterInstrument}
          onChange={(e) => setFilterInstrument(e.target.value)}
          className="max-w-[200px]"
        />
        <Input
          placeholder="Filter status..."
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="max-w-[200px]"
        />
      </div>
      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No trades match filters.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Instrument</TableHead>
              <TableHead>Direction</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Entry</TableHead>
              <TableHead>Exit</TableHead>
              <TableHead>P&L</TableHead>
              <TableHead>Exit Reason</TableHead>
              <TableHead>Time</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((t) => (
              <TableRow key={t.client_order_id}>
                <TableCell className="font-mono">{t.instrument.replace("_", "/")}</TableCell>
                <TableCell><DirectionBadge direction={t.direction} /></TableCell>
                <TableCell><TradeStatusBadge status={t.status} /></TableCell>
                <TableCell className="font-mono">
                  {t.entry_price?.toFixed(t.instrument === "BTC_USD" ? 2 : 5) ?? "-"}
                </TableCell>
                <TableCell className="font-mono">
                  {t.exit_price?.toFixed(t.instrument === "BTC_USD" ? 2 : 5) ?? "-"}
                </TableCell>
                <TableCell
                  className={`font-mono ${
                    t.pnl !== null && t.pnl >= 0 ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {t.pnl !== null ? `$${t.pnl.toFixed(2)}` : "-"}
                </TableCell>
                <TableCell className="text-sm">{t.exit_reason ?? "-"}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {t.created_at ? new Date(t.created_at).toLocaleString() : "-"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

/* ---------- Signal Log Tab ---------- */

function SignalLogTab({
  signals,
}: {
  signals: Record<string, SignalFullResponse | null>;
}) {
  return (
    <div className="space-y-4">
      {INSTRUMENTS.map((inst) => {
        const sig = signals[inst];
        return (
          <Card key={inst}>
            <CardHeader className="pb-2">
              <CardTitle className="font-mono text-base">{inst.replace("_", "/")}</CardTitle>
            </CardHeader>
            <CardContent>
              {sig ? (
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Action:</span>
                    <ActionBadge action={sig.action} />
                  </div>
                  <div>
                    <span className="text-muted-foreground">Probability: </span>
                    <span className="font-mono">{(sig.probability * 100).toFixed(1)}%</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Confidence: </span>
                    <span className="font-mono">{(sig.confidence * 100).toFixed(1)}%</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Generator: </span>
                    <span className="font-mono">{sig.generator_id}</span>
                  </div>
                  {sig.scaffold && (
                    <Badge variant="outline" className="text-yellow-400">Scaffold</Badge>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Signal unavailable</p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

/* ---------- Circuit Breakers Tab ---------- */

function CircuitBreakersTab({ data }: { data: CircuitBreakersResponse | null }) {
  if (!data) {
    return <p className="text-sm text-muted-foreground">Loading circuit breaker data...</p>;
  }

  return (
    <div className="space-y-6">
      {/* System breakers */}
      <div>
        <h3 className="mb-2 text-sm font-semibold text-muted-foreground">System</h3>
        <div className="flex flex-wrap gap-3">
          {data.system_breakers.map((b: CircuitBreakerState) => (
            <BreakerCard key={b.name} breaker={b} />
          ))}
        </div>
      </div>

      {/* Portfolio breakers */}
      <div>
        <h3 className="mb-2 text-sm font-semibold text-muted-foreground">Portfolio</h3>
        <div className="flex flex-wrap gap-3">
          {data.portfolio_breakers.map((b: CircuitBreakerState) => (
            <BreakerCard key={b.name} breaker={b} />
          ))}
        </div>
      </div>

      {/* Per-instrument breakers */}
      {Object.entries(data.instrument_breakers).map(([inst, breakers]) => (
        <div key={inst}>
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
            {inst.replace("_", "/")}
          </h3>
          <div className="flex flex-wrap gap-3">
            {breakers.map((b: CircuitBreakerState) => (
              <BreakerCard key={`${inst}-${b.name}`} breaker={b} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function BreakerCard({ breaker }: { breaker: CircuitBreakerState }) {
  return (
    <Card className="w-[200px]">
      <CardContent className="pt-4 pb-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{breaker.name.replace(/_/g, " ")}</span>
          <StatusBadge tripped={breaker.tripped} />
        </div>
        {breaker.tripped && breaker.reason && (
          <p className="mt-1 text-xs text-muted-foreground">{breaker.reason}</p>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------- Reconciliation Tab ---------- */

function ReconciliationTab({ data }: { data: ReconciliationResponse | null }) {
  if (!data) {
    return <p className="text-sm text-muted-foreground">Loading reconciliation data...</p>;
  }

  if (data.results.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        <p>No reconciliation data. Reconciliation runs when the trading loop is active.</p>
        <p className="mt-1">Unresolved mismatches: {data.unresolved_count}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Unresolved mismatches: <span className="font-semibold">{data.unresolved_count}</span>
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Broker</TableHead>
            <TableHead>Instrument</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Checked At</TableHead>
            <TableHead>Resolved</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.results.map((r, i) => (
            <TableRow key={i}>
              <TableCell>{r.broker}</TableCell>
              <TableCell className="font-mono">{r.instrument.replace("_", "/")}</TableCell>
              <TableCell><ReconStatusBadge status={r.status} /></TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {new Date(r.checked_at).toLocaleString()}
              </TableCell>
              <TableCell>
                {r.resolved ? (
                  <Badge className="bg-green-900 text-green-200 hover:bg-green-900">Yes</Badge>
                ) : (
                  <Badge variant="destructive">No</Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/* ---------- Main Page ---------- */

export function TradingMonitorPage() {
  const [trades, setTrades] = useState<TradeResponse[]>([]);
  const [circuitBreakers, setCircuitBreakers] = useState<CircuitBreakersResponse | null>(null);
  const [reconciliation, setReconciliation] = useState<ReconciliationResponse | null>(null);
  const [signals, setSignals] = useState<Record<string, SignalFullResponse | null>>({});
  const [pausedInstruments, setPausedInstruments] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [killSwitchBusy, setKillSwitchBusy] = useState(false);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [pauseBusy, setPauseBusy] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    const [tradesR, cbR, reconR, pausedR, ...signalResults] = await Promise.allSettled([
      api.trades({ limit: 200 }),
      api.circuitBreakers(),
      api.reconciliation(),
      api.listPaused(),
      ...INSTRUMENTS.map((inst) => api.signal(inst)),
    ]);

    if (tradesR.status === "fulfilled") setTrades(tradesR.value.trades);
    if (cbR.status === "fulfilled") setCircuitBreakers(cbR.value);
    if (reconR.status === "fulfilled") setReconciliation(reconR.value);
    if (pausedR.status === "fulfilled") setPausedInstruments(pausedR.value.paused_instruments);

    const sigs: Record<string, SignalFullResponse | null> = {};
    INSTRUMENTS.forEach((inst, i) => {
      const r = signalResults[i];
      sigs[inst] = r.status === "fulfilled" ? (r.value as SignalFullResponse) : null;
    });
    setSignals(sigs);

    setLastFetch(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  const handleKillSwitch = async () => {
    setKillSwitchBusy(true);
    try {
      if (circuitBreakers?.kill_switch_active) {
        await api.deactivateKillSwitch();
      } else {
        await api.activateKillSwitch("Trading monitor manual activation");
      }
      await fetchAll();
    } catch {
      await fetchAll();
    } finally {
      setKillSwitchBusy(false);
    }
  };

  const handleClosePosition = async (orderId: string) => {
    setClosingId(orderId);
    try {
      // Position close requires broker adapter — may return 503 in dev
      // For now this is a placeholder showing the intent
      await fetchAll();
    } finally {
      setClosingId(null);
    }
  };

  const handleTogglePause = async (instrument: string) => {
    setPauseBusy(instrument);
    try {
      if (pausedInstruments.includes(instrument)) {
        await api.resumeInstrument(instrument);
      } else {
        await api.pauseInstrument(instrument);
      }
      await fetchAll();
    } catch {
      await fetchAll();
    } finally {
      setPauseBusy(null);
    }
  };

  if (loading) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">Trading Monitor</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Trading Monitor</h1>
          {lastFetch && (
            <span className="text-xs text-muted-foreground">
              Last updated: {lastFetch.toLocaleTimeString()}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {circuitBreakers?.kill_switch_active && (
            <Badge variant="destructive" className="text-sm">KILL SWITCH ACTIVE</Badge>
          )}
          <Button
            variant={circuitBreakers?.kill_switch_active ? "outline" : "destructive"}
            size="sm"
            disabled={killSwitchBusy}
            onClick={handleKillSwitch}
          >
            {killSwitchBusy
              ? "..."
              : circuitBreakers?.kill_switch_active
                ? "Deactivate Kill Switch"
                : "Activate Kill Switch"}
          </Button>
        </div>
      </div>

      {/* Instrument Controls */}
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        {INSTRUMENTS.map((inst) => {
          const isPaused = pausedInstruments.includes(inst);
          const openCount = trades.filter((t) => t.instrument === inst && t.status === "OPEN").length;
          return (
            <Card key={inst}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="font-mono text-lg">{inst.replace("_", "/")}</CardTitle>
                  <div className="flex items-center gap-2">
                    {isPaused && <Badge variant="destructive">PAUSED</Badge>}
                    <Badge variant="outline">{openCount} open</Badge>
                    <Button
                      variant={isPaused ? "default" : "outline"}
                      size="sm"
                      disabled={pauseBusy === inst}
                      onClick={() => handleTogglePause(inst)}
                    >
                      {pauseBusy === inst ? "..." : isPaused ? "Resume" : "Pause"}
                    </Button>
                  </div>
                </div>
              </CardHeader>
            </Card>
          );
        })}
      </div>

      {/* Tabbed content */}
      <Tabs defaultValue="positions">
        <TabsList>
          <TabsTrigger value="positions">
            Open Positions ({trades.filter((t) => t.status === "OPEN").length})
          </TabsTrigger>
          <TabsTrigger value="history">Trade History</TabsTrigger>
          <TabsTrigger value="signals">Signal Log</TabsTrigger>
          <TabsTrigger value="breakers">
            Circuit Breakers
            {circuitBreakers?.any_tripped && (
              <span className="ml-1 inline-block h-2 w-2 rounded-full bg-red-500" />
            )}
          </TabsTrigger>
          <TabsTrigger value="reconciliation">
            Reconciliation
            {reconciliation && reconciliation.unresolved_count > 0 && (
              <span className="ml-1 inline-block h-2 w-2 rounded-full bg-orange-500" />
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="positions" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <OpenPositionsTab
                trades={trades}
                onClose={handleClosePosition}
                closingId={closingId}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <TradeHistoryTab trades={trades} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="signals" className="mt-4">
          <SignalLogTab signals={signals} />
        </TabsContent>

        <TabsContent value="breakers" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <CircuitBreakersTab data={circuitBreakers} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reconciliation" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <ReconciliationTab data={reconciliation} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
