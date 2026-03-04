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
import {
  api,
  type RegimeResponse,
  type ModelArtifact,
  type SignalFullResponse,
  type GeneratorsResponse,
  type FeatureMetadataEntry,
  type FeatureRow,
  type ComputeFeaturesResponse,
} from "@/lib/api";

const INSTRUMENTS = ["EUR_USD", "BTC_USD"];
const INTERVALS = ["1m", "5m", "1h", "4h", "1d"];
const MODEL_TYPES = ["bayesian", "xgboost", "meta_learner"];

/* ================================================================
   Shared helpers
   ================================================================ */

function InstrumentSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground shadow-xs"
    >
      {INSTRUMENTS.map((i) => (
        <option key={i} value={i}>
          {i.replace("_", "/")}
        </option>
      ))}
    </select>
  );
}

function ErrorCard({ message }: { message: string }) {
  return (
    <Card className="border-destructive">
      <CardContent className="py-3">
        <p className="text-sm text-destructive-foreground">{message}</p>
      </CardContent>
    </Card>
  );
}

function RegimeBadge({ label }: { label: string }) {
  const colors: Record<string, string> = {
    LOW_VOL_TRENDING: "bg-blue-900 text-blue-200 hover:bg-blue-900",
    LOW_VOL_RANGING: "bg-cyan-900 text-cyan-200 hover:bg-cyan-900",
    HIGH_VOL_TRENDING: "bg-orange-900 text-orange-200 hover:bg-orange-900",
    HIGH_VOL_RANGING: "bg-red-900 text-red-200 hover:bg-red-900",
    UNKNOWN: "bg-zinc-800 text-zinc-400 hover:bg-zinc-800",
  };
  return (
    <Badge className={colors[label] ?? colors.UNKNOWN}>{label.replace(/_/g, " ")}</Badge>
  );
}

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    STRONG_BUY: "bg-green-900 text-green-200 hover:bg-green-900",
    BUY: "bg-emerald-900 text-emerald-200 hover:bg-emerald-900",
    SELL: "bg-red-900 text-red-200 hover:bg-red-900",
    NEUTRAL: "bg-zinc-800 text-zinc-400 hover:bg-zinc-800",
  };
  return <Badge className={colors[action] ?? colors.NEUTRAL}>{action}</Badge>;
}

function ConfidenceBadge({ band }: { band: string }) {
  const colors: Record<string, string> = {
    HIGH: "bg-green-900 text-green-200 hover:bg-green-900",
    MEDIUM: "bg-yellow-900 text-yellow-200 hover:bg-yellow-900",
    LOW: "bg-red-900 text-red-200 hover:bg-red-900",
  };
  return <Badge className={colors[band] ?? colors.LOW}>{band}</Badge>;
}

/* ================================================================
   1. Feature Explorer
   ================================================================ */

function FeatureExplorer() {
  const [instrument, setInstrument] = useState(INSTRUMENTS[0]);
  const [interval, setInterval_] = useState("1h");
  const [metadata, setMetadata] = useState<FeatureMetadataEntry[]>([]);
  const [rows, setRows] = useState<FeatureRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [computing, setComputing] = useState(false);
  const [computeResult, setComputeResult] = useState<ComputeFeaturesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load feature metadata on mount
  useEffect(() => {
    api
      .featuresMetadata()
      .then((data) => setMetadata(data.registry))
      .catch(() => setMetadata([]));
  }, []);

  const fetchFeatures = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const start = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      const data = await api.features(instrument, {
        interval,
        start,
        limit: 5000,
      });
      setRows(data.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load features");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [instrument, interval]);

  const computeFeatures = useCallback(async () => {
    setComputing(true);
    setError(null);
    setComputeResult(null);
    try {
      const result = await api.computeFeatures(instrument, interval);
      setComputeResult(result);
      // Auto-load features after computing
      await fetchFeatures();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feature computation failed");
    } finally {
      setComputing(false);
    }
  }, [instrument, interval, fetchFeatures]);

  // Pivot rows into a table: timestamps as rows, feature_keys as columns
  const pivoted = pivotFeatures(rows);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            Technical indicators are mathematical calculations derived from raw price and
            volume data (OHLCV candles). Newton computes five core indicators:{" "}
            <strong>RSI</strong> (Relative Strength Index — measures momentum, 0-100),{" "}
            <strong>MACD</strong> (Moving Average Convergence/Divergence — trend
            direction and strength), <strong>Bollinger Bands</strong> (volatility
            envelope around price), <strong>OBV</strong> (On-Balance Volume — volume
            flow), and <strong>ATR</strong> (Average True Range — volatility magnitude).
            These features feed into the signal generation engines.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            If the table is empty, click <strong>Compute Features</strong> to calculate
            indicators from stored candle data. This reads OHLCV from the database,
            runs the indicator pipeline, and saves results.
          </p>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <InstrumentSelect value={instrument} onChange={setInstrument} />
        <select
          value={interval}
          onChange={(e) => setInterval_(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground shadow-xs"
        >
          {INTERVALS.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
        <Button onClick={fetchFeatures} disabled={loading || computing}>
          {loading ? "Loading..." : "Load Features"}
        </Button>
        <Button variant="outline" onClick={computeFeatures} disabled={loading || computing}>
          {computing ? "Computing..." : "Compute Features"}
        </Button>
        {metadata.length > 0 && (
          <span className="text-xs text-muted-foreground">
            {metadata.length} indicators registered
          </span>
        )}
      </div>

      {computeResult && (
        <Card>
          <CardContent className="py-3">
            <p className="text-sm text-green-400">
              Computed {computeResult.features_computed.toLocaleString()} feature values
              from {computeResult.candles_read.toLocaleString()} candles
              ({computeResult.instrument}/{computeResult.interval})
            </p>
          </CardContent>
        </Card>
      )}

      {error && <ErrorCard message={error} />}

      {pivoted.timestamps.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 bg-background">Time</TableHead>
                {pivoted.keys.map((k) => (
                  <TableHead key={k} className="text-right whitespace-nowrap">
                    {k}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {pivoted.timestamps.map((ts) => (
                <TableRow key={ts}>
                  <TableCell className="sticky left-0 bg-background font-mono text-xs whitespace-nowrap">
                    {new Date(ts).toLocaleString()}
                  </TableCell>
                  {pivoted.keys.map((k) => (
                    <TableCell key={k} className="text-right font-mono text-xs">
                      {pivoted.grid[ts]?.[k] != null
                        ? formatNum(pivoted.grid[ts][k])
                        : "—"}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {!loading && !computing && rows.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          No feature data found. Click <strong>Compute Features</strong> to
          calculate indicators from stored candle data, then{" "}
          <strong>Load Features</strong> to view the results.
        </p>
      )}
    </div>
  );
}

function formatNum(v: number): string {
  if (Math.abs(v) >= 1000) return v.toFixed(2);
  if (Math.abs(v) >= 1) return v.toFixed(4);
  return v.toFixed(6);
}

function pivotFeatures(rows: FeatureRow[]) {
  const keySet = new Set<string>();
  const tsSet = new Set<string>();
  const grid: Record<string, Record<string, number>> = {};

  for (const r of rows) {
    keySet.add(r.feature_key);
    tsSet.add(r.time);
    if (!grid[r.time]) grid[r.time] = {};
    grid[r.time][r.feature_key] = r.value;
  }

  const keys = [...keySet].sort();
  const timestamps = [...tsSet].sort().slice(-50); // Latest 50 timestamps
  return { keys, timestamps, grid };
}

/* ================================================================
   2. Signal Inspector
   ================================================================ */

function SignalInspector() {
  const [instrument, setInstrument] = useState(INSTRUMENTS[0]);
  const [generators, setGenerators] = useState<GeneratorsResponse | null>(null);
  const [selectedGen, setSelectedGen] = useState<string>("");
  const [signal, setSignal] = useState<SignalFullResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .generators()
      .then((data) => setGenerators(data))
      .catch(() => setGenerators(null));
  }, []);

  const generate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.signal(instrument, selectedGen || undefined);
      setSignal(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signal generation failed");
      setSignal(null);
    } finally {
      setLoading(false);
    }
  }, [instrument, selectedGen]);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            Newton generates trading signals by analyzing market data through
            multiple engines. Each engine produces a probability estimate
            (0-100%) of a profitable trade opportunity, which is then converted
            into an action: <strong>STRONG_BUY</strong> (high probability — open
            full position), <strong>BUY</strong> (moderate — open smaller
            position), <strong>SELL</strong> (close existing position), or{" "}
            <strong>NEUTRAL</strong> (no action).
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Three signal engines are available:{" "}
            <strong>bayesian_v1</strong> (statistical inference using token
            patterns), <strong>ml_v1</strong> (XGBoost machine learning model),
            and <strong>ensemble_v1</strong> (combines both via a meta-learner).
            The system routes each instrument to a primary engine with automatic
            fallback if the primary fails. Component scores show the individual
            contribution from each engine.
          </p>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <InstrumentSelect value={instrument} onChange={setInstrument} />
        {generators && (
          <select
            value={selectedGen}
            onChange={(e) => setSelectedGen(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground shadow-xs"
          >
            <option value="">Default routing</option>
            {generators.generators.map((g) => (
              <option key={g.id} value={g.id}>
                {g.id} {g.enabled ? "" : "(disabled)"}
              </option>
            ))}
          </select>
        )}
        <Button onClick={generate} disabled={loading}>
          {loading ? "Generating..." : "Generate Signal"}
        </Button>
      </div>

      {error && <ErrorCard message={error} />}

      {signal && (
        <div className="grid gap-4 md:grid-cols-2">
          {/* Signal summary card */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Signal Result</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">Action:</span>
                <ActionBadge action={signal.action} />
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">Probability:</span>
                <span className="font-mono text-sm">
                  {(signal.probability * 100).toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">Confidence:</span>
                <span className="font-mono text-sm">
                  {(signal.confidence * 100).toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">Generator:</span>
                <Badge variant="outline">{signal.generator_id}</Badge>
              </div>
              <div className="text-xs text-muted-foreground">
                {new Date(signal.generated_at).toLocaleString()}
              </div>
              {signal.warning && (
                <p className="text-xs text-yellow-500">{signal.warning}</p>
              )}
            </CardContent>
          </Card>

          {/* Component scores card */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Component Scores</CardTitle>
            </CardHeader>
            <CardContent>
              {Object.keys(signal.component_scores).length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Component</TableHead>
                      <TableHead className="text-right">Score</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(signal.component_scores).map(([k, v]) => (
                      <TableRow key={k}>
                        <TableCell className="font-mono text-xs">{k}</TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {(v * 100).toFixed(1)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">No component scores</p>
              )}

              {/* Metadata */}
              {Object.keys(signal.metadata).length > 0 && (
                <div className="mt-4">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    Metadata
                  </p>
                  <pre className="whitespace-pre-wrap rounded bg-muted p-2 text-xs">
                    {JSON.stringify(signal.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {!loading && !signal && !error && (
        <p className="text-sm text-muted-foreground">
          Click &quot;Generate Signal&quot; to trigger signal generation.
        </p>
      )}
    </div>
  );
}

/* ================================================================
   3. Regime Monitor
   ================================================================ */

function RegimeMonitor() {
  const [regimes, setRegimes] = useState<Record<string, RegimeResponse>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(
        INSTRUMENTS.map((inst) => api.regime(inst)),
      );
      const map: Record<string, RegimeResponse> = {};
      for (const r of results) {
        map[r.instrument] = r;
      }
      setRegimes(map);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load regime data");
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-load on mount
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            Markets behave differently depending on current conditions. Newton
            classifies each instrument into one of four regime states based on
            two measurements:{" "}
            <strong>vol_30d</strong> (30-day annualized volatility — how much
            prices are fluctuating) and <strong>ADX_14</strong> (14-day Average
            Directional Index — how strongly prices are trending, scale 0-100).
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            The four regimes are: <strong>LOW VOL TRENDING</strong> (calm market
            with clear direction), <strong>LOW VOL RANGING</strong> (calm with no
            clear direction), <strong>HIGH VOL TRENDING</strong> (volatile with
            clear direction), and <strong>HIGH VOL RANGING</strong> (volatile and
            choppy). The <strong>confidence band</strong> indicates how clearly the
            market fits its classification: HIGH (strong signal), MEDIUM (moderate),
            or LOW (uncertain — the system reduces position sizes as a safety
            measure). vol_median is the historical median volatility used as the
            dividing line between &quot;low&quot; and &quot;high&quot; volatility.
          </p>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={fetchAll} disabled={loading}>
          {loading ? "Loading..." : "Refresh Regime"}
        </Button>
      </div>

      {error && <ErrorCard message={error} />}

      {Object.keys(regimes).length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {INSTRUMENTS.map((inst) => {
            const r = regimes[inst];
            if (!r) return null;
            return (
              <Card key={inst}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    {inst.replace("_", "/")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">Regime:</span>
                    <RegimeBadge label={r.regime_label} />
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">Confidence:</span>
                    <span className="font-mono text-sm">
                      {(r.confidence * 100).toFixed(1)}%
                    </span>
                    <ConfidenceBadge band={r.confidence_band} />
                  </div>
                  <Table>
                    <TableBody>
                      <TableRow>
                        <TableCell className="text-muted-foreground">vol_30d</TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {r.vol_30d.toFixed(4)}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell className="text-muted-foreground">ADX_14</TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {r.adx_14.toFixed(2)}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell className="text-muted-foreground">vol_median</TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {r.vol_median.toFixed(4)}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                  <div className="text-xs text-muted-foreground">
                    Computed: {new Date(r.computed_at).toLocaleString()}
                  </div>
                  {r.error && (
                    <p className="text-xs text-yellow-500">{r.error}</p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {!loading && Object.keys(regimes).length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          Click &quot;Refresh Regime&quot; to load current regime state.
        </p>
      )}
    </div>
  );
}

/* ================================================================
   4. Model Dashboard
   ================================================================ */

function ModelDashboard() {
  const [instrument, setInstrument] = useState(INSTRUMENTS[0]);
  const [modelType, setModelType] = useState("");
  const [artifacts, setArtifacts] = useState<ModelArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedVersion, setExpandedVersion] = useState<string | null>(null);

  const fetchModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.models(instrument, modelType || undefined);
      setArtifacts(data.artifacts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load models");
      setArtifacts([]);
    } finally {
      setLoading(false);
    }
  }, [instrument, modelType]);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            Newton trains machine learning models to predict profitable trading
            opportunities. Three model types work together:{" "}
            <strong>bayesian</strong> (statistical pattern matching using token
            likelihoods), <strong>xgboost</strong> (gradient-boosted decision
            trees trained on historical features), and{" "}
            <strong>meta_learner</strong> (logistic regression that combines the
            other two into a final probability estimate).
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Each model version is stored with its training date, hyperparameters
            (settings used during training), and performance metrics. The key
            metric is <strong>AUC-ROC</strong> (Area Under the ROC Curve) which
            measures how well the model distinguishes good trades from bad ones
            — 0.50 is random guessing, 1.00 is perfect prediction. Models are
            only used in production if their AUC exceeds a minimum threshold.
            Click a row to see full details.
          </p>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <InstrumentSelect value={instrument} onChange={setInstrument} />
        <select
          value={modelType}
          onChange={(e) => setModelType(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground shadow-xs"
        >
          <option value="">All model types</option>
          {MODEL_TYPES.map((mt) => (
            <option key={mt} value={mt}>
              {mt}
            </option>
          ))}
        </select>
        <Button onClick={fetchModels} disabled={loading}>
          {loading ? "Loading..." : "Load Models"}
        </Button>
      </div>

      {error && <ErrorCard message={error} />}

      {artifacts.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Type</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Training Date</TableHead>
              <TableHead className="text-right">AUC-ROC</TableHead>
              <TableHead className="text-right">Data Hash</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {artifacts.map((a) => {
              const key = `${a.model_type}-v${a.version}`;
              const auc = a.performance_metrics["auc_roc"] ?? a.performance_metrics["auc"];
              const expanded = expandedVersion === key;
              return (
                <>
                  <TableRow
                    key={key}
                    className="cursor-pointer select-none hover:bg-muted/40"
                    onClick={() => setExpandedVersion(expanded ? null : key)}
                  >
                    <TableCell className="font-mono text-xs">
                      <span className="mr-1 inline-block w-3 text-muted-foreground">
                        {expanded ? "\u25BE" : "\u25B8"}
                      </span>
                      {a.model_type}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">v{a.version}</Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {new Date(a.training_date).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {auc != null ? auc.toFixed(4) : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {a.data_hash.slice(0, 12)}...
                    </TableCell>
                  </TableRow>
                  {expanded && (
                    <TableRow key={`${key}-detail`}>
                      <TableCell colSpan={5} className="bg-muted/50 px-4 py-3">
                        <div className="space-y-2 text-xs">
                          <div>
                            <span className="font-medium text-muted-foreground">
                              Hyperparameters:
                            </span>
                            <pre className="mt-1 whitespace-pre-wrap rounded bg-muted p-2">
                              {JSON.stringify(a.hyperparameters, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <span className="font-medium text-muted-foreground">
                              Performance Metrics:
                            </span>
                            <pre className="mt-1 whitespace-pre-wrap rounded bg-muted p-2">
                              {JSON.stringify(a.performance_metrics, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <span className="font-medium text-muted-foreground">
                              Artifact Hash:
                            </span>{" "}
                            <span className="font-mono">{a.artifact_hash}</span>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              );
            })}
          </TableBody>
        </Table>
      )}

      {!loading && artifacts.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          Click &quot;Load Models&quot; to view model artifacts. No models will
          appear until the ML pipeline has been trained.
        </p>
      )}
    </div>
  );
}

/* ================================================================
   Main Admin Page
   ================================================================ */

export function AdminPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Admin</h1>
      <Tabs defaultValue="features">
        <TabsList>
          <TabsTrigger value="features">Feature Explorer</TabsTrigger>
          <TabsTrigger value="signals">Signal Inspector</TabsTrigger>
          <TabsTrigger value="regime">Regime Monitor</TabsTrigger>
          <TabsTrigger value="models">Model Dashboard</TabsTrigger>
        </TabsList>
        <TabsContent value="features" className="mt-4">
          <FeatureExplorer />
        </TabsContent>
        <TabsContent value="signals" className="mt-4">
          <SignalInspector />
        </TabsContent>
        <TabsContent value="regime" className="mt-4">
          <RegimeMonitor />
        </TabsContent>
        <TabsContent value="models" className="mt-4">
          <ModelDashboard />
        </TabsContent>
      </Tabs>
    </div>
  );
}
