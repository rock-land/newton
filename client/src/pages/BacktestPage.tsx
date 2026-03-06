import { useState, useCallback, useEffect, useMemo } from "react";
import {
  AreaChart,
  Area,
  Bar,
  ErrorBar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  ScatterChart,
  Scatter,
  Line,
  ComposedChart,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  type BacktestRegimeResponse,
  type CalibrationDecile,
  type OHLCVCandle,
} from "@/lib/api";

/* ---------- Constants ---------- */

const INSTRUMENTS = ["EUR_USD", "BTC_USD"];

const REGIME_COLORS: Record<string, string> = {
  LOW_VOL_TRENDING: "rgba(34, 197, 94, 0.10)",
  LOW_VOL_RANGING: "rgba(59, 130, 246, 0.10)",
  HIGH_VOL_TRENDING: "rgba(249, 115, 22, 0.10)",
  HIGH_VOL_RANGING: "rgba(239, 68, 68, 0.10)",
  UNKNOWN: "rgba(107, 114, 128, 0.05)",
};

const REGIME_STROKE: Record<string, string> = {
  LOW_VOL_TRENDING: "#22c55e",
  LOW_VOL_RANGING: "#3b82f6",
  HIGH_VOL_TRENDING: "#f97316",
  HIGH_VOL_RANGING: "#ef4444",
  UNKNOWN: "#6b7280",
};

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

function diffColor(a: number, b: number, higherIsBetter: boolean): string {
  if (a === b) return "";
  const better = higherIsBetter ? a > b : a < b;
  return better ? "text-green-400" : "text-red-400";
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

/* ---------- Regime breakdown from trades ---------- */

interface RegimeSpan {
  startTime: string;
  endTime: string;
  regime: string;
}

function getRegimeSpans(trades: BacktestTradeResponse[]): RegimeSpan[] {
  if (trades.length === 0) return [];
  const sorted = [...trades].sort(
    (a, b) => new Date(a.entry_time).getTime() - new Date(b.entry_time).getTime(),
  );
  const spans: RegimeSpan[] = [];
  let current = sorted[0].regime_label;
  let start = sorted[0].entry_time;

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].regime_label !== current) {
      spans.push({
        startTime: fmtDate(start),
        endTime: fmtDate(sorted[i - 1].exit_time ?? sorted[i - 1].entry_time),
        regime: current,
      });
      current = sorted[i].regime_label;
      start = sorted[i].entry_time;
    }
  }
  const last = sorted[sorted.length - 1];
  spans.push({
    startTime: fmtDate(start),
    endTime: fmtDate(last.exit_time ?? last.entry_time),
    regime: current,
  });
  return spans;
}

/* ---------- Equity Chart with Regime Overlay ---------- */

function EquityChart({
  result,
  showRegime,
}: {
  result: BacktestResultResponse;
  showRegime: boolean;
}) {
  const data = result.equity_curve.map((p) => ({
    time: fmtDate(p.time),
    equity: Number(p.equity.toFixed(2)),
  }));

  const regimeSpans = showRegime ? getRegimeSpans(result.trades) : [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          Equity Curve
          {showRegime && regimeSpans.length > 0 && (
            <span className="text-xs text-muted-foreground ml-2 font-normal">
              (regime shading)
            </span>
          )}
        </CardTitle>
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
              formatter={(value) => [
                `$${Number(value).toLocaleString()}`,
                "Equity",
              ]}
            />
            {showRegime &&
              regimeSpans.map((span, i) => (
                <ReferenceArea
                  key={i}
                  x1={span.startTime}
                  x2={span.endTime}
                  fill={REGIME_COLORS[span.regime] ?? REGIME_COLORS.UNKNOWN}
                  fillOpacity={1}
                  strokeOpacity={0}
                />
              ))}
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
        {showRegime && regimeSpans.length > 0 && (
          <div className="flex flex-wrap gap-3 mt-2">
            {Object.entries(REGIME_STROKE).map(([label, color]) => (
              <div key={label} className="flex items-center gap-1.5 text-xs">
                <div
                  className="size-3 rounded-sm"
                  style={{ backgroundColor: color }}
                />
                <span className="text-muted-foreground">
                  {label.replace(/_/g, " ")}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------- Calibration Chart ---------- */

function CalibrationChart({
  deciles,
  calibrationError,
}: {
  deciles: CalibrationDecile[];
  calibrationError: number;
}) {
  if (deciles.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Calibration Plot
            <span className="text-xs text-muted-foreground ml-2 font-normal">
              (no per-decile data available)
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Calibration error: {fmtPct(calibrationError)}. Per-decile data will
            be available when signal probabilities are included in backtests.
          </p>
        </CardContent>
      </Card>
    );
  }

  const data = deciles.map((d) => ({
    predicted: Number(d.predicted_mid.toFixed(3)),
    observed: Number(d.observed_freq.toFixed(3)),
    count: d.count,
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          Calibration Plot
          <Badge className="ml-2 text-xs" variant="outline">
            Error: {fmtPct(calibrationError)}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis
              dataKey="predicted"
              name="Predicted"
              domain={[0, 1]}
              tick={{ fontSize: 11, fill: "#999" }}
              label={{
                value: "Predicted Probability",
                position: "insideBottom",
                offset: -5,
                style: { fill: "#999", fontSize: 11 },
              }}
            />
            <YAxis
              dataKey="observed"
              name="Observed"
              domain={[0, 1]}
              tick={{ fontSize: 11, fill: "#999" }}
              label={{
                value: "Observed Frequency",
                angle: -90,
                position: "insideLeft",
                style: { fill: "#999", fontSize: 11 },
              }}
            />
            <RechartsTooltip
              contentStyle={{
                backgroundColor: "#1c1c1c",
                border: "1px solid #333",
                borderRadius: 6,
                fontSize: 12,
              }}
              formatter={(value?: number, name?: string) => [
                fmt(value ?? 0, 3),
                name ?? "",
              ]}
            />
            <ReferenceLine
              segment={[
                { x: 0, y: 0 },
                { x: 1, y: 1 },
              ]}
              stroke="#555"
              strokeDasharray="5 5"
              label={{
                value: "Perfect",
                position: "insideTopLeft",
                style: { fill: "#555", fontSize: 10 },
              }}
            />
            <Scatter data={data} fill="#8b5cf6" />
          </ScatterChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

/* ---------- Regime Breakdown Table ---------- */

function RegimeBreakdownTable({
  breakdown,
  lowSampleRegimes,
}: {
  breakdown: Record<string, BacktestRegimeResponse>;
  lowSampleRegimes: string[];
}) {
  const regimes = Object.values(breakdown);
  if (regimes.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          Regime Breakdown ({regimes.length} regimes)
        </CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Regime</TableHead>
              <TableHead className="text-right">Trades</TableHead>
              <TableHead className="text-right">Sharpe</TableHead>
              <TableHead className="text-right">PF</TableHead>
              <TableHead className="text-right">Win Rate</TableHead>
              <TableHead className="text-right">Total PnL</TableHead>
              <TableHead>Flag</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {regimes.map((r) => (
              <TableRow key={r.regime_label}>
                <TableCell className="flex items-center gap-2">
                  <div
                    className="size-3 rounded-sm"
                    style={{
                      backgroundColor:
                        REGIME_STROKE[r.regime_label] ?? "#6b7280",
                    }}
                  />
                  <span className="text-sm">
                    {r.regime_label.replace(/_/g, " ")}
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {r.trade_count}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {fmt(r.sharpe_ratio)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {fmt(r.profit_factor)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {fmtPct(r.win_rate)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono text-xs ${pnlColor(r.total_pnl)}`}
                >
                  {fmt(r.total_pnl)}
                </TableCell>
                <TableCell>
                  {r.low_sample_flag && (
                    <Badge variant="outline" className="text-yellow-400 border-yellow-800 text-xs">
                      Low Sample
                    </Badge>
                  )}
                  {lowSampleRegimes.includes(r.regime_label) && !r.low_sample_flag && (
                    <Badge variant="outline" className="text-yellow-400 border-yellow-800 text-xs">
                      Excluded
                    </Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/* ---------- Candlestick Chart with Trade Overlay ---------- */

interface CandleChartData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  body: [number, number];
  errorY: [number, number];
  isUp: boolean;
}

function CandlestickShape(props: Record<string, unknown>) {
  const { x, y, width, height, payload } = props as {
    x: number;
    y: number;
    width: number;
    height: number;
    payload: CandleChartData;
  };
  const color = payload.isUp ? "#22c55e" : "#ef4444";
  return (
    <rect
      x={x}
      y={y}
      width={width}
      height={Math.max(height, 1)}
      fill={color}
      stroke={color}
    />
  );
}

function CandlestickChart({
  result,
}: {
  result: BacktestResultResponse;
}) {
  const [candles, setCandles] = useState<OHLCVCandle[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .ohlcv(result.instrument, {
        interval: "1h",
        start: result.equity_curve[0]?.time ?? new Date().toISOString(),
        limit: 5000,
      })
      .then((res) => {
        if (!cancelled) setCandles(res.data);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Failed to load OHLCV data",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [result.instrument, result.equity_curve]);

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Price Chart</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Loading OHLCV data...</p>
        </CardContent>
      </Card>
    );
  }

  if (error || !candles || candles.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Price Chart</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {error ??
              "No OHLCV data available. The chart requires historical candle data in the database."}
          </p>
        </CardContent>
      </Card>
    );
  }

  // Downsample if too many candles
  const maxCandles = 500;
  const step = Math.max(1, Math.floor(candles.length / maxCandles));
  const sampled = candles.filter((_, i) => i % step === 0);

  const chartData: CandleChartData[] = sampled.map((c) => {
    const isUp = c.close >= c.open;
    const bodyLow = Math.min(c.open, c.close);
    const bodyHigh = Math.max(c.open, c.close);
    return {
      time: fmtDate(c.time),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      body: [bodyLow, bodyHigh],
      errorY: [bodyLow - c.low, c.high - bodyHigh],
      isUp,
    };
  });

  // Trade markers
  const entries = result.trades.map((t) => ({
    time: fmtDate(t.entry_time),
    price: t.entry_price,
    direction: t.direction,
    type: "entry" as const,
  }));
  const exits = result.trades
    .filter((t) => t.exit_time && t.exit_price != null)
    .map((t) => ({
      time: fmtDate(t.exit_time!),
      price: t.exit_price!,
      direction: t.direction,
      type: "exit" as const,
    }));

  // Merge trade markers into chart data lookup
  const tradeMarkerMap = new Map<string, { entries: typeof entries; exits: typeof exits }>();
  for (const e of entries) {
    if (!tradeMarkerMap.has(e.time)) tradeMarkerMap.set(e.time, { entries: [], exits: [] });
    tradeMarkerMap.get(e.time)!.entries.push(e);
  }
  for (const e of exits) {
    if (!tradeMarkerMap.has(e.time)) tradeMarkerMap.set(e.time, { entries: [], exits: [] });
    tradeMarkerMap.get(e.time)!.exits.push(e);
  }

  // Regime spans for shading
  const regimeSpans = getRegimeSpans(result.trades);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          Price Chart — {result.instrument.replace("_", "/")}
          <span className="text-xs text-muted-foreground ml-2 font-normal">
            ({sampled.length} candles)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#999" }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 11, fill: "#999" }}
              tickFormatter={(v: number) => v.toFixed(result.instrument === "BTC_USD" ? 0 : 4)}
            />
            <RechartsTooltip
              contentStyle={{
                backgroundColor: "#1c1c1c",
                border: "1px solid #333",
                borderRadius: 6,
                fontSize: 12,
              }}
              formatter={(_v?: unknown, _n?: string, item?: { payload?: CandleChartData }) => {
                const c = item?.payload;
                if (!c) return ["", ""];
                return [
                  `O: ${c.open} H: ${c.high} L: ${c.low} C: ${c.close}`,
                  "OHLC",
                ];
              }}
            />
            {regimeSpans.map((span, i) => (
              <ReferenceArea
                key={i}
                x1={span.startTime}
                x2={span.endTime}
                fill={REGIME_COLORS[span.regime] ?? REGIME_COLORS.UNKNOWN}
                fillOpacity={1}
                strokeOpacity={0}
              />
            ))}
            <Bar
              dataKey="body"
              barSize={Math.max(1, Math.min(6, 400 / sampled.length))}
              shape={<CandlestickShape />}
              isAnimationActive={false}
            >
              <ErrorBar
                dataKey="errorY"
                direction="y"
                width={0}
                stroke="#999"
                strokeWidth={1}
              />
            </Bar>
            {/* Entry markers */}
            {entries.slice(0, 200).map((e, i) => (
              <ReferenceLine
                key={`entry-${i}`}
                x={e.time}
                stroke={e.direction === "BUY" ? "#22c55e" : "#ef4444"}
                strokeDasharray="2 2"
                strokeWidth={1}
                strokeOpacity={0.6}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
        <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-0.5 bg-green-500" style={{ borderTop: "1px dashed #22c55e" }} />
            BUY entry
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-0.5 bg-red-500" style={{ borderTop: "1px dashed #ef4444" }} />
            SELL entry
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------- Trade Table ---------- */

function TradeTable({ trades }: { trades: BacktestTradeResponse[] }) {
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const totalPages = Math.ceil(trades.length / pageSize);
  const visible = trades.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center justify-between">
          <span>Trade List ({trades.length} trades)</span>
          {totalPages > 1 && (
            <div className="flex items-center gap-2 text-xs font-normal">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                Prev
              </Button>
              <span className="text-muted-foreground">
                {page + 1} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
              >
                Next
              </Button>
            </div>
          )}
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
            {visible.map((t, i) => {
              const totalCost = t.commission + t.slippage_cost + t.spread_cost;
              return (
                <TableRow key={page * pageSize + i}>
                  <TableCell className="text-muted-foreground text-xs">
                    {page * pageSize + i + 1}
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

/* ---------- Results View (enhanced) ---------- */

function ResultsView({ run }: { run: BacktestRunStatusResponse }) {
  const [showRegime, setShowRegime] = useState(true);

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

      {/* Equity curve with regime toggle */}
      <div className="flex items-center gap-2 mb-1">
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={showRegime}
            onChange={(e) => setShowRegime(e.target.checked)}
            className="size-4 rounded border-input"
          />
          Regime overlay
        </label>
      </div>
      <EquityChart result={r} showRegime={showRegime} />

      {/* Regime breakdown table */}
      <RegimeBreakdownTable
        breakdown={r.regime_breakdown}
        lowSampleRegimes={r.low_sample_regimes}
      />

      {/* Calibration plot */}
      <CalibrationChart
        deciles={m.calibration_deciles}
        calibrationError={m.calibration_error}
      />

      {/* Candlestick chart with trade overlay */}
      <CandlestickChart result={r} />

      {/* Trade list */}
      <TradeTable trades={r.trades} />
    </div>
  );
}

/* ---------- Backtest History ---------- */

function BacktestHistory({
  onSelect,
}: {
  onSelect: (run: BacktestRunStatusResponse) => void;
}) {
  const [runs, setRuns] = useState<BacktestRunStatusResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listBacktests();
      setRuns(res.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleLoadRun = useCallback(
    async (id: string) => {
      try {
        const full = await api.getBacktest(id);
        onSelect(full);
      } catch {
        setError("Failed to load backtest run");
      }
    },
    [onSelect],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Backtest History</h2>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {error && (
        <Card className="border-red-900">
          <CardContent className="pt-4">
            <p className="text-red-400 text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {runs.length === 0 && !loading && (
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">
              No backtest runs yet. Run a backtest from the Runner tab.
            </p>
          </CardContent>
        </Card>
      )}

      {runs.length > 0 && (
        <Card>
          <CardContent className="pt-4 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Instrument</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="font-mono text-xs">
                      {run.id}
                    </TableCell>
                    <TableCell className="text-sm">
                      {run.instrument.replace("_", "/")}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {fmtDate(run.start_date)} — {fmtDate(run.end_date)}
                    </TableCell>
                    <TableCell>
                      {run.pessimistic ? (
                        <Badge variant="outline" className="text-yellow-400 border-yellow-800 text-xs">
                          Pessimistic
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs">Normal</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={
                          run.status === "completed"
                            ? "bg-green-900 text-green-200"
                            : run.status === "failed"
                              ? "bg-red-900 text-red-200"
                              : "bg-yellow-900 text-yellow-200"
                        }
                      >
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {fmtDateTime(run.created_at)}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleLoadRun(run.id)}
                      >
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ---------- Backtest Comparison ---------- */

interface CompareMetric {
  label: string;
  key: keyof BacktestResultResponse["metrics"];
  format: (n: number) => string;
  higherIsBetter: boolean;
}

const COMPARE_METRICS: CompareMetric[] = [
  { label: "Sharpe Ratio", key: "sharpe_ratio", format: (n) => fmt(n), higherIsBetter: true },
  { label: "Profit Factor", key: "profit_factor", format: (n) => fmt(n), higherIsBetter: true },
  { label: "Max Drawdown", key: "max_drawdown", format: fmtPct, higherIsBetter: false },
  { label: "Win Rate", key: "win_rate", format: fmtPct, higherIsBetter: true },
  { label: "Expectancy", key: "expectancy", format: (n) => fmt(n), higherIsBetter: true },
  { label: "Calmar Ratio", key: "calmar_ratio", format: (n) => fmt(n), higherIsBetter: true },
  { label: "Calibration Error", key: "calibration_error", format: fmtPct, higherIsBetter: false },
  { label: "Ann. Return", key: "annualized_return", format: fmtPct, higherIsBetter: true },
  { label: "Total Return", key: "total_return", format: fmtPct, higherIsBetter: true },
  { label: "Trade Count", key: "trade_count", format: (n) => String(n), higherIsBetter: true },
];

function BacktestComparison() {
  const [runs, setRuns] = useState<BacktestRunStatusResponse[]>([]);
  const [runA, setRunA] = useState<BacktestRunStatusResponse | null>(null);
  const [runB, setRunB] = useState<BacktestRunStatusResponse | null>(null);
  const [selectedA, setSelectedA] = useState("");
  const [selectedB, setSelectedB] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .listBacktests()
      .then((res) => setRuns(res.runs))
      .catch(() => {});
  }, []);

  const loadRun = useCallback(
    async (id: string, target: "A" | "B") => {
      setLoading(true);
      try {
        const full = await api.getBacktest(id);
        if (target === "A") setRunA(full);
        else setRunB(full);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const completedRuns = runs.filter((r) => r.status === "completed");

  const resultA = runA?.result ?? null;
  const resultB = runB?.result ?? null;

  // Overlaid equity curves
  const equityOverlay = useMemo(() => {
    if (!resultA && !resultB) return [];
    const mapA = new Map(
      (resultA?.equity_curve ?? []).map((p) => [fmtDate(p.time), p.equity]),
    );
    const mapB = new Map(
      (resultB?.equity_curve ?? []).map((p) => [fmtDate(p.time), p.equity]),
    );
    const allTimes = new Set([...mapA.keys(), ...mapB.keys()]);
    return [...allTimes]
      .sort()
      .map((time) => ({
        time,
        equityA: mapA.get(time) ?? null,
        equityB: mapB.get(time) ?? null,
      }));
  }, [resultA, resultB]);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Compare Backtests</h2>

      {/* Selectors */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-4">
            <label className="text-xs text-muted-foreground block mb-1">
              Run A
            </label>
            <select
              value={selectedA}
              onChange={(e) => {
                setSelectedA(e.target.value);
                if (e.target.value) loadRun(e.target.value, "A");
              }}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Select a run...</option>
              {completedRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} — {r.instrument.replace("_", "/")} ({fmtDate(r.start_date)})
                  {r.pessimistic ? " [P]" : ""}
                </option>
              ))}
            </select>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <label className="text-xs text-muted-foreground block mb-1">
              Run B
            </label>
            <select
              value={selectedB}
              onChange={(e) => {
                setSelectedB(e.target.value);
                if (e.target.value) loadRun(e.target.value, "B");
              }}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Select a run...</option>
              {completedRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} — {r.instrument.replace("_", "/")} ({fmtDate(r.start_date)})
                  {r.pessimistic ? " [P]" : ""}
                </option>
              ))}
            </select>
          </CardContent>
        </Card>
      </div>

      {loading && (
        <p className="text-sm text-muted-foreground">Loading run data...</p>
      )}

      {/* Metric comparison table */}
      {resultA && resultB && (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Metrics Comparison</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead className="text-right">Run A</TableHead>
                    <TableHead className="text-right">Run B</TableHead>
                    <TableHead className="text-right">Diff</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {COMPARE_METRICS.map((cm) => {
                    const a = resultA.metrics[cm.key] as number;
                    const b = resultB.metrics[cm.key] as number;
                    const diff = a - b;
                    return (
                      <TableRow key={cm.key}>
                        <TableCell className="text-sm">{cm.label}</TableCell>
                        <TableCell
                          className={`text-right font-mono text-xs ${diffColor(a, b, cm.higherIsBetter)}`}
                        >
                          {cm.format(a)}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono text-xs ${diffColor(b, a, cm.higherIsBetter)}`}
                        >
                          {cm.format(b)}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono text-xs ${diff > 0 ? (cm.higherIsBetter ? "text-green-400" : "text-red-400") : diff < 0 ? (cm.higherIsBetter ? "text-red-400" : "text-green-400") : ""}`}
                        >
                          {diff > 0 ? "+" : ""}
                          {cm.format(diff)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Overlaid equity curves */}
          {equityOverlay.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Equity Curves (Overlay)</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={320}>
                  <ComposedChart data={equityOverlay}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 11, fill: "#999" }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "#999" }}
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
                    />
                    <Line
                      type="monotone"
                      dataKey="equityA"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={false}
                      name="Run A"
                      connectNulls
                    />
                    <Line
                      type="monotone"
                      dataKey="equityB"
                      stroke="#f97316"
                      strokeWidth={2}
                      dot={false}
                      name="Run B"
                      connectNulls
                    />
                  </ComposedChart>
                </ResponsiveContainer>
                <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-0.5 bg-blue-500" />
                    Run A ({runA?.id})
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-0.5 bg-orange-500" />
                    Run B ({runB?.id})
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Gate comparison */}
          <div className="grid grid-cols-2 gap-4">
            <GateBadges result={resultA} />
            <GateBadges result={resultB} />
          </div>
        </>
      )}
    </div>
  );
}

/* ---------- Main Page ---------- */

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
  const [activeTab, setActiveTab] = useState("runner");

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

  const handleHistorySelect = useCallback(
    (selectedRun: BacktestRunStatusResponse) => {
      setRun(selectedRun);
      setActiveTab("runner");
    },
    [],
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Backtest</h1>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="runner">Runner</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="compare">Compare</TabsTrigger>
        </TabsList>

        {/* Runner Tab */}
        <TabsContent value="runner">
          <div className="space-y-4">
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
                  <Button
                    onClick={handleRun}
                    disabled={loading}
                    className="ml-auto"
                  >
                    {loading ? (
                      <>
                        <span className="animate-spin mr-2">&#9696;</span>
                        Running...
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
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history">
          <BacktestHistory onSelect={handleHistorySelect} />
        </TabsContent>

        {/* Compare Tab */}
        <TabsContent value="compare">
          <BacktestComparison />
        </TabsContent>
      </Tabs>
    </div>
  );
}
