import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  type RegimeResponse,
  type ApiError,
} from "@/lib/api";

/* ---------- Constants ---------- */

const INSTRUMENTS = ["EUR_USD", "BTC_USD"];

const REGIME_LABELS = [
  "TRENDING_QUIET",
  "TRENDING_VOLATILE",
  "RANGING_QUIET",
  "RANGING_VOLATILE",
  "UNKNOWN",
];

/* ---------- Risk field metadata ---------- */

interface RiskFieldMeta {
  key: string;
  label: string;
  section: "defaults" | "portfolio";
  type: "float" | "int";
  min?: number;
  max?: number;
  step?: number;
}

const RISK_FIELDS: RiskFieldMeta[] = [
  { key: "max_position_pct", label: "Max Position %", section: "defaults", type: "float", min: 0.005, max: 0.20, step: 0.005 },
  { key: "max_risk_per_trade_pct", label: "Max Risk/Trade %", section: "defaults", type: "float", min: 0.001, max: 0.05, step: 0.001 },
  { key: "kelly_fraction", label: "Kelly Fraction", section: "defaults", type: "float", min: 0.10, max: 0.50, step: 0.01 },
  { key: "kelly_min_trades", label: "Kelly Min Trades", section: "defaults", type: "int", min: 1 },
  { key: "kelly_window", label: "Kelly Window", section: "defaults", type: "int", min: 1 },
  { key: "micro_size_pct", label: "Micro Size %", section: "defaults", type: "float", min: 0.0001, step: 0.001 },
  { key: "hard_stop_pct", label: "Hard Stop %", section: "defaults", type: "float", min: 0.005, max: 0.10, step: 0.005 },
  { key: "trailing_activation_pct", label: "Trailing Activation %", section: "defaults", type: "float", min: 0.0001, step: 0.001 },
  { key: "trailing_breakeven_pct", label: "Trailing Breakeven %", section: "defaults", type: "float", min: 0.0001, step: 0.001 },
  { key: "time_stop_hours", label: "Time Stop (hours)", section: "defaults", type: "int", min: 1, max: 168 },
  { key: "daily_loss_limit_pct", label: "Daily Loss Limit %", section: "defaults", type: "float", min: 0.005, max: 0.05, step: 0.005 },
  { key: "max_drawdown_pct", label: "Max Drawdown %", section: "defaults", type: "float", min: 0.05, max: 0.30, step: 0.01 },
  { key: "consecutive_loss_halt", label: "Consecutive Loss Halt", section: "defaults", type: "int", min: 1 },
  { key: "consecutive_loss_halt_hours", label: "Loss Halt Hours", section: "defaults", type: "int", min: 1 },
  { key: "gap_risk_multiplier", label: "Gap Risk Multiplier", section: "defaults", type: "float", min: 0.0001, step: 0.1 },
  { key: "volatility_threshold_multiplier", label: "Vol Threshold Multiplier", section: "defaults", type: "float", min: 0.0001, step: 0.1 },
  { key: "high_volatility_size_reduction", label: "High Vol Size Reduction", section: "defaults", type: "float", min: 0.0001, max: 1, step: 0.05 },
  { key: "high_volatility_stop_pct", label: "High Vol Stop %", section: "defaults", type: "float", min: 0.0001, step: 0.005 },
  { key: "max_total_exposure_pct", label: "Max Total Exposure %", section: "portfolio", type: "float", min: 0.0001, max: 1, step: 0.05 },
  { key: "max_portfolio_drawdown_pct", label: "Max Portfolio Drawdown %", section: "portfolio", type: "float", min: 0.0001, max: 1, step: 0.01 },
];

/* ---------- Risk Parameters Tab ---------- */

function RiskParametersTab() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await api.getRiskConfig();
      setConfig(res.config);
      setEdits({});
      setMessage(null);
    } catch {
      setMessage({ type: "error", text: "Failed to load risk config" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  if (loading) return <p className="text-muted-foreground p-4">Loading risk configuration...</p>;
  if (!config) return <p className="text-destructive p-4">Failed to load risk configuration.</p>;

  const defaults = (config.defaults ?? {}) as Record<string, unknown>;
  const portfolio = (config.portfolio ?? {}) as Record<string, unknown>;

  function getCurrentValue(field: RiskFieldMeta): unknown {
    return field.section === "defaults" ? defaults[field.key] : portfolio[field.key];
  }

  function getEditKey(field: RiskFieldMeta): string {
    return `${field.section}.${field.key}`;
  }

  function handleFieldChange(field: RiskFieldMeta, value: string) {
    const editKey = getEditKey(field);
    const current = String(getCurrentValue(field) ?? "");
    if (value === current) {
      const next = { ...edits };
      delete next[editKey];
      setEdits(next);
    } else {
      setEdits({ ...edits, [editKey]: value });
    }
  }

  const hasEdits = Object.keys(edits).length > 0;

  async function handleSave() {
    setSaving(true);
    setMessage(null);

    const defaultsUpdate: Record<string, unknown> = {};
    const portfolioUpdate: Record<string, unknown> = {};

    for (const [editKey, val] of Object.entries(edits)) {
      const [section, key] = editKey.split(".");
      const field = RISK_FIELDS.find((f) => f.section === section && f.key === key);
      if (!field) continue;
      const parsed = field.type === "int" ? parseInt(val, 10) : parseFloat(val);
      if (isNaN(parsed)) {
        setMessage({ type: "error", text: `Invalid value for ${field.label}` });
        setSaving(false);
        return;
      }
      if (section === "defaults") defaultsUpdate[key] = parsed;
      else portfolioUpdate[key] = parsed;
    }

    try {
      const res = await api.updateRiskConfig({
        defaults: Object.keys(defaultsUpdate).length > 0 ? defaultsUpdate : undefined,
        portfolio: Object.keys(portfolioUpdate).length > 0 ? portfolioUpdate : undefined,
        reason: "Updated via Config UI",
        changed_by: "ui",
      });
      setConfig(res.config);
      setEdits({});
      setMessage({ type: "success", text: "Risk configuration saved successfully" });
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      const detail = typeof apiErr.body === "object" && apiErr.body !== null && "detail" in apiErr.body
        ? String((apiErr.body as Record<string, unknown>).detail)
        : apiErr.message;
      setMessage({ type: "error", text: `Save failed: ${detail}` });
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setEdits({});
    setMessage(null);
  }

  const defaultFields = RISK_FIELDS.filter((f) => f.section === "defaults");
  const portfolioFields = RISK_FIELDS.filter((f) => f.section === "portfolio");

  return (
    <div className="space-y-4">
      {message && (
        <div
          className={`rounded-md px-4 py-2 text-sm ${
            message.type === "success"
              ? "bg-green-900/50 text-green-200 border border-green-800"
              : "bg-red-900/50 text-red-200 border border-red-800"
          }`}
        >
          {message.text}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Default Risk Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[250px]">Parameter</TableHead>
                <TableHead className="w-[120px]">Current</TableHead>
                <TableHead className="w-[150px]">New Value</TableHead>
                <TableHead>Constraints</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {defaultFields.map((field) => {
                const editKey = getEditKey(field);
                const current = getCurrentValue(field);
                const edited = edits[editKey];
                return (
                  <TableRow key={editKey}>
                    <TableCell className="font-medium">{field.label}</TableCell>
                    <TableCell className="font-mono text-sm">{String(current ?? "—")}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step={field.step ?? "any"}
                        min={field.min}
                        max={field.max}
                        value={edited ?? String(current ?? "")}
                        onChange={(e) => handleFieldChange(field, e.target.value)}
                        className="h-8 w-32 font-mono text-sm"
                      />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {field.min !== undefined && `min: ${field.min}`}
                      {field.min !== undefined && field.max !== undefined && " · "}
                      {field.max !== undefined && `max: ${field.max}`}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Portfolio Risk Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[250px]">Parameter</TableHead>
                <TableHead className="w-[120px]">Current</TableHead>
                <TableHead className="w-[150px]">New Value</TableHead>
                <TableHead>Constraints</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {portfolioFields.map((field) => {
                const editKey = getEditKey(field);
                const current = getCurrentValue(field);
                const edited = edits[editKey];
                return (
                  <TableRow key={editKey}>
                    <TableCell className="font-medium">{field.label}</TableCell>
                    <TableCell className="font-mono text-sm">{String(current ?? "—")}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step={field.step ?? "any"}
                        min={field.min}
                        max={field.max}
                        value={edited ?? String(current ?? "")}
                        onChange={(e) => handleFieldChange(field, e.target.value)}
                        className="h-8 w-32 font-mono text-sm"
                      />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {field.min !== undefined && `min: ${field.min}`}
                      {field.min !== undefined && field.max !== undefined && " · "}
                      {field.max !== undefined && `max: ${field.max}`}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex gap-2">
        <Button onClick={handleSave} disabled={!hasEdits || saving}>
          {saving ? "Saving..." : "Save Changes"}
        </Button>
        <Button variant="outline" onClick={handleReset} disabled={!hasEdits}>
          Reset
        </Button>
      </div>
    </div>
  );
}

/* ---------- Regime Overrides Tab ---------- */

function RegimeOverridesTab() {
  const [regimes, setRegimes] = useState<Record<string, RegimeResponse>>({});
  const [loading, setLoading] = useState(true);
  const [overrideForm, setOverrideForm] = useState<{
    instrument: string;
    label: string;
    reason: string;
  } | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchRegimes = useCallback(async () => {
    const results = await Promise.allSettled(
      INSTRUMENTS.map((inst) => api.regime(inst)),
    );
    const next: Record<string, RegimeResponse> = {};
    results.forEach((r, i) => {
      if (r.status === "fulfilled") next[INSTRUMENTS[i]] = r.value;
    });
    setRegimes(next);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchRegimes();
  }, [fetchRegimes]);

  async function handleSetOverride(instrument: string, label: string, reason: string) {
    setMessage(null);
    try {
      await api.setRegimeOverride(instrument, { regime_label: label, reason });
      setMessage({ type: "success", text: `Override set for ${instrument}: ${label}` });
      setOverrideForm(null);
      fetchRegimes();
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setMessage({ type: "error", text: `Failed: ${apiErr.message}` });
    }
  }

  async function handleClearOverride(instrument: string) {
    setMessage(null);
    try {
      await api.clearRegimeOverride(instrument);
      setMessage({ type: "success", text: `Override cleared for ${instrument}` });
      fetchRegimes();
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setMessage({ type: "error", text: `Failed: ${apiErr.message}` });
    }
  }

  if (loading) return <p className="text-muted-foreground p-4">Loading regime data...</p>;

  return (
    <div className="space-y-4">
      {message && (
        <div
          className={`rounded-md px-4 py-2 text-sm ${
            message.type === "success"
              ? "bg-green-900/50 text-green-200 border border-green-800"
              : "bg-red-900/50 text-red-200 border border-red-800"
          }`}
        >
          {message.text}
        </div>
      )}

      {INSTRUMENTS.map((inst) => {
        const regime = regimes[inst];
        const isOverridden = regime?.override_active ?? false;

        return (
          <Card key={inst}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">{inst}</CardTitle>
                <div className="flex items-center gap-2">
                  {isOverridden && (
                    <Badge className="bg-yellow-900 text-yellow-200 hover:bg-yellow-900">
                      OVERRIDE
                    </Badge>
                  )}
                  <RegimeBadge label={regime?.regime_label ?? "UNKNOWN"} />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Confidence:</span>{" "}
                    <span className="font-mono">{regime?.confidence?.toFixed(4) ?? "—"}</span>
                    {regime?.confidence_band && (
                      <Badge variant="outline" className="ml-2 text-xs">
                        {regime.confidence_band}
                      </Badge>
                    )}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Vol 30d:</span>{" "}
                    <span className="font-mono">{regime?.vol_30d?.toFixed(6) ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">ADX 14:</span>{" "}
                    <span className="font-mono">{regime?.adx_14?.toFixed(2) ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Vol Median:</span>{" "}
                    <span className="font-mono">{regime?.vol_median?.toFixed(6) ?? "—"}</span>
                  </div>
                </div>

                {regime?.error && (
                  <p className="text-xs text-yellow-400">Note: {regime.error}</p>
                )}

                <div className="flex gap-2 pt-2">
                  {isOverridden ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleClearOverride(inst)}
                    >
                      Clear Override
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setOverrideForm({ instrument: inst, label: "TRENDING_QUIET", reason: "" })
                      }
                    >
                      Set Override
                    </Button>
                  )}
                </div>

                {overrideForm?.instrument === inst && (
                  <div className="border border-border rounded-md p-3 space-y-2 mt-2">
                    <div className="flex gap-2 items-center">
                      <label className="text-sm text-muted-foreground w-16">Label:</label>
                      <select
                        value={overrideForm.label}
                        onChange={(e) =>
                          setOverrideForm({ ...overrideForm, label: e.target.value })
                        }
                        className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                      >
                        {REGIME_LABELS.map((l) => (
                          <option key={l} value={l}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex gap-2 items-center">
                      <label className="text-sm text-muted-foreground w-16">Reason:</label>
                      <Input
                        value={overrideForm.reason}
                        onChange={(e) =>
                          setOverrideForm({ ...overrideForm, reason: e.target.value })
                        }
                        placeholder="Reason for override"
                        className="h-8 text-sm"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() =>
                          handleSetOverride(inst, overrideForm.label, overrideForm.reason || "Manual override via UI")
                        }
                      >
                        Apply
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setOverrideForm(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function RegimeBadge({ label }: { label: string }) {
  const colorMap: Record<string, string> = {
    TRENDING_QUIET: "bg-blue-900 text-blue-200 hover:bg-blue-900",
    TRENDING_VOLATILE: "bg-purple-900 text-purple-200 hover:bg-purple-900",
    RANGING_QUIET: "bg-green-900 text-green-200 hover:bg-green-900",
    RANGING_VOLATILE: "bg-orange-900 text-orange-200 hover:bg-orange-900",
    UNKNOWN: "bg-zinc-800 text-zinc-300 hover:bg-zinc-800",
  };
  return (
    <Badge className={colorMap[label] ?? colorMap.UNKNOWN}>{label}</Badge>
  );
}

/* ---------- Trading Mode Tab ---------- */

function TradingModeTab() {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trading Mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Current Mode:</span>
            <Badge className="bg-yellow-900 text-yellow-200 hover:bg-yellow-900">
              PAPER
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Live trading mode will be available in Stage 8 (Paper Trading).
            The system currently operates in paper mode only.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">System Info</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium">Supported Instruments</TableCell>
                <TableCell>EUR_USD, BTC_USD</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Brokers</TableCell>
                <TableCell>Oanda (EUR/USD), Binance (BTC/USD)</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Signal Interval</TableCell>
                <TableCell>1h</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">API Version</TableCell>
                <TableCell>v1</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

/* ---------- Main Page ---------- */

export function ConfigPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System Configuration</h1>
        <p className="text-sm text-muted-foreground">
          Manage risk parameters, regime overrides, and system settings.
        </p>
      </div>

      <Tabs defaultValue="risk">
        <TabsList>
          <TabsTrigger value="risk">Risk Parameters</TabsTrigger>
          <TabsTrigger value="regime">Regime Overrides</TabsTrigger>
          <TabsTrigger value="mode">Trading Mode</TabsTrigger>
        </TabsList>
        <TabsContent value="risk">
          <RiskParametersTab />
        </TabsContent>
        <TabsContent value="regime">
          <RegimeOverridesTab />
        </TabsContent>
        <TabsContent value="mode">
          <TradingModeTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
