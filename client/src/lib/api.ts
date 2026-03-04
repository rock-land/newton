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

/* ---------- Endpoints ---------- */

export const api = {
  health: () => request<HealthResponse>("/health"),

  generators: () => request<GeneratorInfo[]>("/signals/generators"),

  signal: (instrument: string, generator?: string) => {
    const params = generator ? `?generator=${encodeURIComponent(generator)}` : "";
    return request<SignalResponse>(`/signals/${encodeURIComponent(instrument)}${params}`);
  },

  ohlcv: (instrument: string, params?: { interval?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.interval) qs.set("interval", params.interval);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<unknown>(`/ohlcv/${encodeURIComponent(instrument)}${suffix}`);
  },

  featuresMetadata: () => request<unknown>("/features/metadata"),

  features: (instrument: string, params?: { interval?: string; namespace?: string }) => {
    const qs = new URLSearchParams();
    if (params?.interval) qs.set("interval", params.interval);
    if (params?.namespace) qs.set("namespace", params.namespace);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<unknown>(`/features/${encodeURIComponent(instrument)}${suffix}`);
  },
};
