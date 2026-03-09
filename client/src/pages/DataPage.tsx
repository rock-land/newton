import { useState, useCallback, useMemo } from "react";
import {
  Bar,
  ErrorBar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
  Line,
  ComposedChart,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  api,
  type OHLCVCandle,
  type FeatureRow,
} from "@/lib/api";

/* ---------- Constants ---------- */

const INSTRUMENTS = ["EUR_USD", "BTC_USD"] as const;
const INTERVALS = ["1m", "5m", "1h", "4h", "1d"] as const;
const DEFAULT_LIMIT = 200;

/** Feature key patterns for the indicators we support overlaying. */
const INDICATOR_GROUPS = {
  RSI: { keys: ["rsi:period=14"], label: "RSI (14)", panel: "rsi" as const },
  MACD: {
    keys: [
      "macd:fast=12,slow=26,signal=9:line",
      "macd:fast=12,slow=26,signal=9:signal",
      "macd:fast=12,slow=26,signal=9:histogram",
    ],
    label: "MACD (12,26,9)",
    panel: "macd" as const,
  },
  BB: {
    keys: [
      "bb:period=20,std=2.0:upper",
      "bb:period=20,std=2.0:middle",
      "bb:period=20,std=2.0:lower",
    ],
    label: "Bollinger Bands (20,2)",
    panel: "price" as const,
  },
} as const;

type IndicatorKey = keyof typeof INDICATOR_GROUPS;

/* ---------- Helpers ---------- */

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function defaultStart(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 16);
}

/* ---------- Chart data types ---------- */

interface CandleChartRow {
  time: string;
  rawTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  body: [number, number];
  errorY: [number, number];
  isUp: boolean;
  // Indicator overlays
  rsi?: number;
  macd_line?: number;
  macd_signal?: number;
  macd_histogram?: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
}

/* ---------- Candlestick shape ---------- */

function CandlestickShape(props: Record<string, unknown>) {
  const { x, y, width, height, payload } = props as {
    x: number;
    y: number;
    width: number;
    height: number;
    payload: CandleChartRow;
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

/* ---------- Volume bar shape ---------- */

function VolumeBarShape(props: Record<string, unknown>) {
  const { x, y, width, height, payload } = props as {
    x: number;
    y: number;
    width: number;
    height: number;
    payload: CandleChartRow;
  };
  const color = payload.isUp ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)";
  return (
    <rect
      x={x}
      y={y}
      width={width}
      height={Math.max(height, 0)}
      fill={color}
    />
  );
}

/* ---------- Feature key to chart field mapping ---------- */

const FEATURE_KEY_TO_FIELD: Record<string, keyof CandleChartRow> = {
  "rsi:period=14": "rsi",
  "macd:fast=12,slow=26,signal=9:line": "macd_line",
  "macd:fast=12,slow=26,signal=9:signal": "macd_signal",
  "macd:fast=12,slow=26,signal=9:histogram": "macd_histogram",
  "bb:period=20,std=2.0:upper": "bb_upper",
  "bb:period=20,std=2.0:middle": "bb_middle",
  "bb:period=20,std=2.0:lower": "bb_lower",
};

/* ---------- Main component ---------- */

export function DataPage() {
  const [instrument, setInstrument] = useState<string>(INSTRUMENTS[0]);
  const [interval, setInterval] = useState<string>("1h");
  const [start, setStart] = useState(defaultStart);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);

  const [candles, setCandles] = useState<OHLCVCandle[] | null>(null);
  const [features, setFeatures] = useState<FeatureRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [activeIndicators, setActiveIndicators] = useState<Set<IndicatorKey>>(
    new Set(),
  );

  const toggleIndicator = useCallback((key: IndicatorKey) => {
    setActiveIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const startISO = new Date(start).toISOString();
      const ohlcvRes = await api.ohlcv(instrument, {
        interval,
        start: startISO,
        limit,
      });
      setCandles(ohlcvRes.data);

      // Fetch features for active indicators
      const allKeys = Array.from(activeIndicators).flatMap(
        (k) => INDICATOR_GROUPS[k].keys,
      );
      if (allKeys.length > 0) {
        const featRes = await api.features(instrument, {
          interval,
          start: startISO,
          limit,
          indicators: allKeys.join(","),
        });
        setFeatures(featRes.data);
      } else {
        setFeatures([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data");
      setCandles(null);
      setFeatures([]);
    } finally {
      setLoading(false);
    }
  }, [instrument, interval, start, limit, activeIndicators]);

  // Build chart data by merging candles + features
  const chartData = useMemo<CandleChartRow[]>(() => {
    if (!candles || candles.length === 0) return [];

    // Index features by time+key for fast lookup
    const featureMap = new Map<string, number>();
    for (const f of features) {
      featureMap.set(`${f.time}|${f.feature_key}`, f.value);
    }

    return candles.map((c) => {
      const isUp = c.close >= c.open;
      const bodyLow = Math.min(c.open, c.close);
      const bodyHigh = Math.max(c.open, c.close);

      const row: CandleChartRow = {
        time: fmtTime(c.time),
        rawTime: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
        body: [bodyLow, bodyHigh],
        errorY: [bodyLow - c.low, c.high - bodyHigh],
        isUp,
      };

      // Merge indicator values
      for (const [fKey, field] of Object.entries(FEATURE_KEY_TO_FIELD)) {
        const val = featureMap.get(`${c.time}|${fKey}`);
        if (val !== undefined) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (row as any)[field] = val;
        }
      }

      return row;
    });
  }, [candles, features]);

  const isBTC = instrument === "BTC_USD";
  const pricePrecision = isBTC ? 0 : 4;
  const barSize = Math.max(1, Math.min(6, 600 / Math.max(chartData.length, 1)));

  const showRSI = activeIndicators.has("RSI") && chartData.some((r) => r.rsi != null);
  const showMACD =
    activeIndicators.has("MACD") && chartData.some((r) => r.macd_line != null);
  const showBB =
    activeIndicators.has("BB") && chartData.some((r) => r.bb_upper != null);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Data Viewer</h1>

      {/* Controls */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-3">
            {/* Instrument */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Instrument</label>
              <select
                className="block rounded-md border bg-background px-3 py-1.5 text-sm"
                value={instrument}
                onChange={(e) => setInstrument(e.target.value)}
              >
                {INSTRUMENTS.map((i) => (
                  <option key={i} value={i}>
                    {i.replace("_", "/")}
                  </option>
                ))}
              </select>
            </div>

            {/* Interval */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Interval</label>
              <select
                className="block rounded-md border bg-background px-3 py-1.5 text-sm"
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
              >
                {INTERVALS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </div>

            {/* Start date */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Start</label>
              <Input
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="w-48 text-sm"
              />
            </div>

            {/* Limit */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Limit</label>
              <Input
                type="number"
                min={1}
                max={10000}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) || DEFAULT_LIMIT)}
                className="w-24 text-sm"
              />
            </div>

            {/* Fetch */}
            <Button onClick={fetchData} disabled={loading} size="sm">
              {loading ? "Loading..." : "Fetch"}
            </Button>
          </div>

          {/* Indicator toggles */}
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="text-xs text-muted-foreground self-center">
              Indicators:
            </span>
            {(Object.keys(INDICATOR_GROUPS) as IndicatorKey[]).map((key) => (
              <Badge
                key={key}
                variant={activeIndicators.has(key) ? "default" : "outline"}
                className="cursor-pointer select-none"
                onClick={() => toggleIndicator(key)}
              >
                {INDICATOR_GROUPS[key].label}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-4">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {candles && candles.length === 0 && !loading && (
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">
              No candle data found for the selected range.
            </p>
          </CardContent>
        </Card>
      )}

      {chartData.length > 0 && (
        <>
          {/* Price chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                {instrument.replace("_", "/")} — {interval}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  ({chartData.length} candles)
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={380}>
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
                    tickFormatter={(v: number) => v.toFixed(pricePrecision)}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "#1c1c1c",
                      border: "1px solid #333",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                    formatter={(
                      _v?: unknown,
                      name?: string,
                      item?: { payload?: CandleChartRow },
                    ) => {
                      const c = item?.payload;
                      if (!c) return ["", ""];
                      if (name === "body") {
                        return [
                          `O: ${c.open.toFixed(pricePrecision)}  H: ${c.high.toFixed(pricePrecision)}  L: ${c.low.toFixed(pricePrecision)}  C: ${c.close.toFixed(pricePrecision)}`,
                          "OHLC",
                        ];
                      }
                      return [
                        typeof _v === "number" ? _v.toFixed(pricePrecision) : String(_v),
                        name ?? "",
                      ];
                    }}
                  />
                  {/* Candlesticks */}
                  <Bar
                    dataKey="body"
                    barSize={barSize}
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
                  {/* Bollinger Bands overlay */}
                  {showBB && (
                    <>
                      <Line
                        dataKey="bb_upper"
                        stroke="#8b5cf6"
                        strokeWidth={1}
                        dot={false}
                        strokeDasharray="4 2"
                        isAnimationActive={false}
                        connectNulls
                      />
                      <Line
                        dataKey="bb_middle"
                        stroke="#8b5cf6"
                        strokeWidth={1}
                        dot={false}
                        isAnimationActive={false}
                        connectNulls
                      />
                      <Line
                        dataKey="bb_lower"
                        stroke="#8b5cf6"
                        strokeWidth={1}
                        dot={false}
                        strokeDasharray="4 2"
                        isAnimationActive={false}
                        connectNulls
                      />
                    </>
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Volume chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base text-muted-foreground">Volume</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={120}>
                <ComposedChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="time" tick={false} />
                  <YAxis
                    tick={{ fontSize: 10, fill: "#999" }}
                    tickFormatter={(v: number) =>
                      v >= 1_000_000
                        ? `${(v / 1_000_000).toFixed(1)}M`
                        : v >= 1_000
                          ? `${(v / 1_000).toFixed(0)}K`
                          : String(v)
                    }
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "#1c1c1c",
                      border: "1px solid #333",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                    formatter={(v: unknown) => [
                      typeof v === "number" ? v.toLocaleString() : String(v),
                      "Volume",
                    ]}
                  />
                  <Bar
                    dataKey="volume"
                    barSize={barSize}
                    shape={<VolumeBarShape />}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* RSI panel */}
          {showRSI && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-muted-foreground">
                  RSI (14)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={150}>
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="time" tick={false} />
                    <YAxis
                      domain={[0, 100]}
                      ticks={[0, 30, 50, 70, 100]}
                      tick={{ fontSize: 10, fill: "#999" }}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: "#1c1c1c",
                        border: "1px solid #333",
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                      formatter={(v: unknown) => [
                        typeof v === "number" ? v.toFixed(2) : String(v),
                        "RSI",
                      ]}
                    />
                    <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.5} />
                    <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="3 3" strokeOpacity={0.5} />
                    <Line
                      dataKey="rsi"
                      stroke="#f59e0b"
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* MACD panel */}
          {showMACD && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-muted-foreground">
                  MACD (12, 26, 9)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={150}>
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="time" tick={false} />
                    <YAxis
                      domain={["auto", "auto"]}
                      tick={{ fontSize: 10, fill: "#999" }}
                      tickFormatter={(v: number) => v.toFixed(isBTC ? 0 : 5)}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: "#1c1c1c",
                        border: "1px solid #333",
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                    />
                    <ReferenceLine y={0} stroke="#666" strokeWidth={1} />
                    <Bar
                      dataKey="macd_histogram"
                      barSize={barSize}
                      isAnimationActive={false}
                      fill="#6366f1"
                      fillOpacity={0.4}
                    />
                    <Line
                      dataKey="macd_line"
                      stroke="#3b82f6"
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls
                      name="MACD"
                    />
                    <Line
                      dataKey="macd_signal"
                      stroke="#f97316"
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls
                      name="Signal"
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Data table summary */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base text-muted-foreground">
                Summary
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-4">
                <div>
                  <span className="text-muted-foreground">Candles: </span>
                  {chartData.length}
                </div>
                <div>
                  <span className="text-muted-foreground">First: </span>
                  {fmtTime(chartData[0].rawTime)}
                </div>
                <div>
                  <span className="text-muted-foreground">Last: </span>
                  {fmtTime(chartData[chartData.length - 1].rawTime)}
                </div>
                <div>
                  <span className="text-muted-foreground">Range: </span>
                  {Math.min(...chartData.map((c) => c.low)).toFixed(pricePrecision)}
                  {" — "}
                  {Math.max(...chartData.map((c) => c.high)).toFixed(pricePrecision)}
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
