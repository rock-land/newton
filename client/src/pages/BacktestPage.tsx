import { useState, useCallback } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
  type BacktestRunStatusResponse,
  type BacktestResultResponse,
  type BacktestTradeResponse,
} from "@/lib/api";

/* ---------- Helpers ---------- */

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals);
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(2)}%`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA");
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-CA")} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
}

function pnlColor(pnl: number): string {
  if (pnl > 0) return "text-green-400";
  if (pnl < 0) return "text-red-400";
  return "text-muted-foreground";
}

/* ---------- Metric Card ---------- */

function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 px-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xl font-semibold mt-1">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

/* ---------- Gate Badges ---------- */

function GateBadges({ result }: { result: BacktestResultResponse }) {
  const gate = result.gate_evaluation;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          Gate Evaluation
          {gate.all_hard_gates_passed ? (
            <Badge className="bg-green-900 text-green-200 hover:bg-green-900">
              ALL PASSED
            </Badge>
          ) : (
            <Badge variant="destructive">FAILED</Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {gate.results.map((g) => (
            <Badge
              key={g.metric_name}
              className={
                g.passed
                  ? "bg-green-900 text-green-200 hover:bg-green-900"
                  : "bg-red-900 text-red-200 hover:bg-red-900"
              }
            >
              {g.metric_name}: {fmt(g.value)} {g.passed ? "PASS" : "FAIL"} (
              {g.gate_type})
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------- Equity Chart ---------- */

function EquityChart({ result }: { result: BacktestResultResponse }) {
  const data = result.equity_curve.map((p) => ({
    time: fmtDate(p.time),
    equity: Number(p.equity.toFixed(2)),
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Equity Curve</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 11, fill: "#999" }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#999" }}
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v: number) => v.toLocaleString()}
            />
            <RechartsTooltip
              contentStyle={{
                backgroundColor: "#1c1c1c",
                border: "1px solid #333",
                borderRadius: 6,
                fontSize: 12,
              }}
              labelStyle={{ color: "#999" }}
              formatter={(value) => [`$${Number(value).toLocaleString()}`, "Equity"]}
            />
            <Area
              type="monotone"
              dataKey="equity"
              stroke="#3b82f6"
              fill="#3b82f6"
              fillOpacity={0.15}
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

/* ---------- Trade Table ---------- */

function TradeTable({ trades }: { trades: BacktestTradeResponse[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          Trade List ({trades.length} trades)
        </CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>#</TableHead>
              <TableHead>Entry</TableHead>
              <TableHead>Exit</TableHead>
              <TableHead>Dir</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Entry Price</TableHead>
              <TableHead className="text-right">Exit Price</TableHead>
              <TableHead className="text-right">PnL</TableHead>
              <TableHead className="text-right">Costs</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Regime</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {trades.map((t, i) => {
              const totalCost = t.commission + t.slippage_cost + t.spread_cost;
              return (
                <TableRow key={i}>
                  <TableCell className="text-muted-foreground text-xs">
                    {i + 1}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {fmtDateTime(t.entry_time)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {t.exit_time ? fmtDateTime(t.exit_time) : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={
                        t.direction === "BUY"
                          ? "text-green-400 border-green-800"
                          : "text-red-400 border-red-800"
                      }
                    >
                      {t.direction}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {fmt(t.quantity, 4)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {fmt(t.entry_price, 5)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {t.exit_price != null ? fmt(t.exit_price, 5) : "—"}
                  </TableCell>
                  <TableCell
                    className={`text-right font-mono text-xs ${pnlColor(t.pnl)}`}
                  >
                    {fmt(t.pnl)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs text-muted-foreground">
                    {fmt(totalCost)}
                  </TableCell>
                  <TableCell className="text-xs">{t.exit_reason}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {t.regime_label}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/* ---------- Results View ---------- */

function ResultsView({ run }: { run: BacktestRunStatusResponse }) {
  if (run.status === "failed") {
    return (
      <Card className="border-red-900">
        <CardContent className="pt-4">
          <p className="text-red-400 font-medium">Backtest failed</p>
          <p className="text-sm text-muted-foreground mt-1">
            {run.error ?? "Unknown error"}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!run.result) return null;

  const r = run.result;
  const m = r.metrics;

  return (
    <div className="space-y-4">
      {/* Summary metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
        <MetricCard label="Sharpe Ratio" value={fmt(m.sharpe_ratio)} />
        <MetricCard label="Profit Factor" value={fmt(m.profit_factor)} />
        <MetricCard label="Max Drawdown" value={fmtPct(m.max_drawdown)} />
        <MetricCard label="Win Rate" value={fmtPct(m.win_rate)} />
        <MetricCard label="Expectancy" value={fmt(m.expectancy)} />
        <MetricCard label="Calmar Ratio" value={fmt(m.calmar_ratio)} />
        <MetricCard label="Calibration Error" value={fmtPct(m.calibration_error)} />
        <MetricCard label="Trades" value={String(m.trade_count)} />
        <MetricCard
          label="Return"
          value={fmtPct(r.total_return)}
          sub={`$${fmt(r.initial_equity)} → $${fmt(r.final_equity)}`}
        />
        <MetricCard label="Ann. Return" value={fmtPct(m.annualized_return)} />
      </div>

      {/* Gate evaluation */}
      <GateBadges result={r} />

      {/* Equity curve */}
      <EquityChart result={r} />

      {/* Trade list */}
      <TradeTable trades={r.trades} />
    </div>
  );
}

/* ---------- Main Page ---------- */

const INSTRUMENTS = ["EUR_USD", "BTC_USD"];

function defaultStartDate(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 2);
  return d.toISOString().slice(0, 10);
}

function defaultEndDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export function BacktestPage() {
  const [instrument, setInstrument] = useState(INSTRUMENTS[0]);
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(defaultEndDate);
  const [pessimistic, setPessimistic] = useState(false);
  const [initialEquity, setInitialEquity] = useState("10000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<BacktestRunStatusResponse | null>(null);

  const handleRun = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRun(null);
    try {
      const result = await api.runBacktest({
        instrument,
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
        pessimistic,
        initial_equity: Number(initialEquity) || 10_000,
      });
      setRun(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [instrument, startDate, endDate, pessimistic, initialEquity]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Backtest Runner</h1>

      {/* Config form */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Instrument
              </label>
              <select
                value={instrument}
                onChange={(e) => setInstrument(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              >
                {INSTRUMENTS.map((inst) => (
                  <option key={inst} value={inst}>
                    {inst.replace("_", "/")}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Start Date
              </label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-40"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                End Date
              </label>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-40"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Initial Equity ($)
              </label>
              <Input
                type="number"
                value={initialEquity}
                onChange={(e) => setInitialEquity(e.target.value)}
                className="w-32"
                min={1}
              />
            </div>
            <div className="flex items-center gap-2 pb-0.5">
              <input
                type="checkbox"
                id="pessimistic"
                checked={pessimistic}
                onChange={(e) => setPessimistic(e.target.checked)}
                className="size-4 rounded border-input"
              />
              <label htmlFor="pessimistic" className="text-sm">
                Pessimistic mode
              </label>
            </div>
            <Button onClick={handleRun} disabled={loading} className="ml-auto">
              {loading ? (
                <>
                  <span className="animate-spin mr-2">&#9696;</span>
                  Running…
                </>
              ) : (
                "Run Backtest"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card className="border-red-900">
          <CardContent className="pt-4">
            <p className="text-red-400">{error}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Is the API server running?
            </p>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {run && <ResultsView run={run} />}
    </div>
  );
}
