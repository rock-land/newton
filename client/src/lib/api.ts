/** Newton API client — typed fetch wrapper. */

const BASE_URL = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown,
  ) {
    super(`API ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Network Error", "API server unreachable");
  }
  if (!res.ok) {
    const text = await res.text();
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {
      // keep as text
    }
    throw new ApiError(res.status, res.statusText, body);
  }
  return res.json() as Promise<T>;
}

/* ---------- Types ---------- */

export interface BrokerHealth {
  connected: boolean;
  last_response_ms: number | null;
}

export interface InstrumentHealth {
  last_candle_age_seconds: number | null;
  reconciled: boolean;
  regime: string;
  regime_confidence: number;
}

export interface HealthResponse {
  status: string;
  db: boolean;
  brokers: Record<string, BrokerHealth>;
  instruments: Record<string, InstrumentHealth>;
  kill_switch_active: boolean;
  uptime_seconds: number;
  generated_at: string;
  checksum: string;
}

export interface SignalMetadata {
  scaffold: boolean;
  generator_id: string;
  regime?: string;
  regime_confidence?: number;
  [key: string]: unknown;
}

export interface SignalResponse {
  instrument: string;
  action: string;
  probability: number;
  timestamp: string;
  metadata: SignalMetadata;
}

export interface GeneratorInfo {
  generator_id: string;
  instruments: string[];
  description: string;
}

export interface UATSuite {
  id: string;
  name: string;
  test_count: number;
}

export interface UATTestResult {
  id: string;
  name: string;
  suite: string;
  status: string;
  duration_ms: number;
  details: string;
  error: string | null;
}

export interface UATRunSummary {
  total: number;
  passed: number;
  failed: number;
  duration_ms: number;
}

export interface UATSuitesResponse {
  suites: UATSuite[];
}

export interface UATRunResponse {
  results: UATTestResult[];
  summary: UATRunSummary;
}

export interface RegimeResponse {
  instrument: string;
  regime_label: string;
  confidence: number;
  confidence_band: string;
  vol_30d: number;
  adx_14: number;
  vol_median: number;
  computed_at: string;
  error: string | null;
}

export interface ModelArtifact {
  model_type: string;
  instrument: string;
  version: number;
  training_date: string;
  hyperparameters: Record<string, unknown>;
  performance_metrics: Record<string, number>;
  data_hash: string;
  artifact_hash: string;
}

export interface ModelListResponse {
  instrument: string;
  model_type: string | null;
  artifacts: ModelArtifact[];
  count: number;
}

export interface GeneratorsResponse {
  scaffold: boolean;
  count: number;
  generators: { id: string; enabled: boolean; parameters: Record<string, unknown> }[];
}

export interface SignalFullResponse {
  scaffold: boolean;
  warning?: string;
  instrument: string;
  action: string;
  probability: number;
  confidence: number;
  component_scores: Record<string, number>;
  metadata: Record<string, unknown>;
  generated_at: string;
  generator_id: string;
}

export interface FeatureMetadataEntry {
  namespace: string;
  feature_key: string;
  display_name: string;
  description: string;
  unit: string;
  params: Record<string, unknown>;
  provider: string;
}

export interface FeatureMetadataResponse {
  count: number;
  registry: FeatureMetadataEntry[];
}

export interface FeatureRow {
  time: string;
  instrument: string;
  interval: string;
  namespace: string;
  feature_key: string;
  value: number;
}

export interface FeaturesResponse {
  instrument: string;
  interval: string;
  start: string;
  limit: number;
  indicators: string[] | null;
  count: number;
  data: FeatureRow[];
}

export interface ComputeFeaturesResponse {
  instrument: string;
  interval: string;
  candles_read: number;
  features_computed: number;
  metadata_stored: number;
}

/* ---------- OHLCV types ---------- */

export interface OHLCVCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OHLCVResponse {
  instrument: string;
  interval: string;
  start: string;
  limit: number;
  count: number;
  data: OHLCVCandle[];
}

/* ---------- Trading types ---------- */

export interface TradeResponse {
  client_order_id: string;
  broker_order_id: string | null;
  instrument: string;
  broker: string;
  direction: string;
  signal_score: number;
  signal_type: string;
  signal_generator_id: string;
  regime_label: string | null;
  entry_time: string | null;
  entry_price: number | null;
  exit_time: string | null;
  exit_price: number | null;
  quantity: number;
  stop_loss_price: number | null;
  status: string;
  pnl: number | null;
  commission: number | null;
  slippage: number | null;
  exit_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface TradesListResponse {
  trades: TradeResponse[];
  count: number;
}

export interface KillSwitchResponse {
  active: boolean;
  action: string;
  positions_closed: number;
  message: string;
}

/* ---------- Backtest types ---------- */

export interface BacktestRunRequest {
  instrument: string;
  start_date: string;
  end_date: string;
  pessimistic: boolean;
  initial_equity: number;
}

export interface EquityCurvePoint {
  time: string;
  equity: number;
}

export interface BacktestTradeResponse {
  entry_time: string;
  entry_price: number;
  exit_time: string | null;
  exit_price: number | null;
  direction: string;
  quantity: number;
  pnl: number;
  commission: number;
  slippage_cost: number;
  spread_cost: number;
  exit_reason: string;
  regime_label: string;
}

export interface CalibrationDecile {
  bin_index: number;
  predicted_mid: number;
  observed_freq: number;
  count: number;
}

export interface BacktestMetricsResponse {
  sharpe_ratio: number;
  profit_factor: number;
  max_drawdown: number;
  win_rate: number;
  calmar_ratio: number;
  expectancy: number;
  calibration_error: number;
  trade_count: number;
  annualized_return: number;
  total_return: number;
  calibration_deciles: CalibrationDecile[];
}

export interface BacktestGateResultResponse {
  metric_name: string;
  value: number;
  threshold: number;
  gate_type: string;
  passed: boolean;
}

export interface BacktestGateResponse {
  results: BacktestGateResultResponse[];
  all_hard_gates_passed: boolean;
  instrument: string;
}

export interface BacktestRegimeResponse {
  regime_label: string;
  sharpe_ratio: number;
  profit_factor: number;
  win_rate: number;
  trade_count: number;
  total_pnl: number;
  low_sample_flag: boolean;
}

export interface BacktestBiasControlResponse {
  bias_name: string;
  mitigation: string;
  status: string;
}

export interface BacktestResultResponse {
  instrument: string;
  equity_curve: EquityCurvePoint[];
  trades: BacktestTradeResponse[];
  metrics: BacktestMetricsResponse;
  gate_evaluation: BacktestGateResponse;
  regime_breakdown: Record<string, BacktestRegimeResponse>;
  bias_controls: BacktestBiasControlResponse[];
  low_sample_regimes: string[];
  initial_equity: number;
  final_equity: number;
  total_return: number;
  trade_count: number;
}

export interface BacktestRunStatusResponse {
  id: string;
  status: string;
  instrument: string;
  start_date: string;
  end_date: string;
  pessimistic: boolean;
  initial_equity: number;
  created_at: string;
  completed_at: string | null;
  result: BacktestResultResponse | null;
  error: string | null;
}

export interface BacktestListResponse {
  runs: BacktestRunStatusResponse[];
  count: number;
}

/* ---------- Endpoints ---------- */

export const api = {
  health: () => request<HealthResponse>("/health"),

  generators: () => request<GeneratorsResponse>("/signals/generators"),

  signal: (instrument: string, generator?: string) => {
    const params = generator ? `?generator=${encodeURIComponent(generator)}` : "";
    return request<SignalFullResponse>(`/signals/${encodeURIComponent(instrument)}${params}`);
  },

  ohlcv: (
    instrument: string,
    params: { interval: string; start: string; limit?: number },
  ) => {
    const qs = new URLSearchParams();
    qs.set("interval", params.interval);
    qs.set("start", params.start);
    if (params.limit) qs.set("limit", String(params.limit));
    return request<OHLCVResponse>(`/ohlcv/${encodeURIComponent(instrument)}?${qs.toString()}`);
  },

  uatSuites: () => request<UATSuitesResponse>("/uat/suites"),

  uatRun: (opts?: { suite?: string; test_id?: string }) =>
    request<UATRunResponse>("/uat/run", {
      method: "POST",
      body: JSON.stringify(opts ?? {}),
    }),

  featuresMetadata: () => request<FeatureMetadataResponse>("/features/metadata"),

  features: (
    instrument: string,
    params: { interval: string; start: string; limit?: number; indicators?: string },
  ) => {
    const qs = new URLSearchParams();
    qs.set("interval", params.interval);
    qs.set("start", params.start);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.indicators) qs.set("indicators", params.indicators);
    return request<FeaturesResponse>(
      `/features/${encodeURIComponent(instrument)}?${qs.toString()}`,
    );
  },

  computeFeatures: (instrument: string, interval: string) =>
    request<ComputeFeaturesResponse>("/features/compute", {
      method: "POST",
      body: JSON.stringify({ instrument, interval }),
    }),

  regime: (instrument: string) =>
    request<RegimeResponse>(`/regime/${encodeURIComponent(instrument)}`),

  models: (instrument: string, modelType?: string) => {
    const params = modelType ? `?model_type=${encodeURIComponent(modelType)}` : "";
    return request<ModelListResponse>(`/models/${encodeURIComponent(instrument)}${params}`);
  },

  runBacktest: (req: BacktestRunRequest) =>
    request<BacktestRunStatusResponse>("/backtest", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  getBacktest: (id: string) =>
    request<BacktestRunStatusResponse>(`/backtest/${encodeURIComponent(id)}`),

  listBacktests: () => request<BacktestListResponse>("/backtest"),

  trades: (opts?: { instrument?: string; status?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (opts?.instrument) qs.set("instrument", opts.instrument);
    if (opts?.status) qs.set("status", opts.status);
    if (opts?.limit) qs.set("limit", String(opts.limit));
    const q = qs.toString();
    return request<TradesListResponse>(`/trades${q ? `?${q}` : ""}`);
  },

  activateKillSwitch: (reason = "manual_activation") =>
    request<KillSwitchResponse>("/kill", {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  deactivateKillSwitch: () =>
    request<KillSwitchResponse>("/kill?confirm=true", { method: "DELETE" }),
};
