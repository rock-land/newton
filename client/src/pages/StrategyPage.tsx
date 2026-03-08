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
  type StrategyConfigResponse,
  type StrategyVersionEntry,
} from "@/lib/api";

/* ---------- Helpers ---------- */

const INSTRUMENTS = ["EUR_USD", "BTC_USD"];

function formatDate(iso: string | null): string {
  if (!iso) return "N/A";
  return new Date(iso).toLocaleString();
}

/** Compute a simple diff between two JSON objects. Returns entries for changed/added/removed keys. */
function jsonDiff(
  a: Record<string, unknown>,
  b: Record<string, unknown>,
  prefix = "",
): { key: string; left: string; right: string; status: "changed" | "added" | "removed" }[] {
  const results: { key: string; left: string; right: string; status: "changed" | "added" | "removed" }[] = [];
  const allKeys = new Set([...Object.keys(a), ...Object.keys(b)]);

  for (const k of allKeys) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    const inA = k in a;
    const inB = k in b;

    if (inA && inB) {
      const va = a[k];
      const vb = b[k];
      if (
        typeof va === "object" && va !== null && !Array.isArray(va) &&
        typeof vb === "object" && vb !== null && !Array.isArray(vb)
      ) {
        results.push(...jsonDiff(va as Record<string, unknown>, vb as Record<string, unknown>, fullKey));
      } else {
        const sa = JSON.stringify(va);
        const sb = JSON.stringify(vb);
        if (sa !== sb) {
          results.push({ key: fullKey, left: sa, right: sb, status: "changed" });
        }
      }
    } else if (inA && !inB) {
      results.push({ key: fullKey, left: JSON.stringify(a[k]), right: "", status: "removed" });
    } else {
      results.push({ key: fullKey, left: "", right: JSON.stringify(b[k]), status: "added" });
    }
  }
  return results;
}

/* ---------- StrategyPage ---------- */

export function StrategyPage() {
  const [instrument, setInstrument] = useState(INSTRUMENTS[0]);
  const [config, setConfig] = useState<StrategyConfigResponse | null>(null);
  const [versions, setVersions] = useState<StrategyVersionEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activating, setActivating] = useState<number | null>(null);

  // Comparison state
  const [diffLeft, setDiffLeft] = useState<number | null>(null);
  const [diffRight, setDiffRight] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [configRes, versionsRes] = await Promise.all([
        api.strategyConfig(instrument),
        api.strategyVersions(instrument),
      ]);
      setConfig(configRes);
      setVersions(versionsRes.versions);
      setDiffLeft(null);
      setDiffRight(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load strategy data");
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleActivate = async (version: number) => {
    setActivating(version);
    try {
      await api.activateStrategy(instrument, version);
      await fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Activation failed");
    } finally {
      setActivating(null);
    }
  };

  // Resolve configs for diff comparison
  const leftConfig = diffLeft !== null
    ? (diffLeft === 0
      ? config?.config
      : versions.find((v) => v.version === diffLeft)?.config)
    : null;
  const rightConfig = diffRight !== null
    ? (diffRight === 0
      ? config?.config
      : versions.find((v) => v.version === diffRight)?.config)
    : null;
  const diffEntries = leftConfig && rightConfig
    ? jsonDiff(leftConfig as Record<string, unknown>, rightConfig as Record<string, unknown>)
    : null;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Strategy Management</h1>
        <select
          value={instrument}
          onChange={(e) => setInstrument(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
        >
          {INSTRUMENTS.map((inst) => (
            <option key={inst} value={inst}>
              {inst.replace("_", "/")}
            </option>
          ))}
        </select>
      </div>

      {/* Error state */}
      {error && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <p className="text-destructive-foreground">{error}</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Is the API server running on port 8000?
            </p>
          </CardContent>
        </Card>
      )}

      {/* Loading state */}
      {loading && (
        <p className="text-muted-foreground">Loading strategy data...</p>
      )}

      {/* Current Config */}
      {config && !loading && (
        <>
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Current Configuration</CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">v{config.version}</Badge>
                  <span className="text-xs text-muted-foreground">
                    Updated: {formatDate(config.updated_at)}
                  </span>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <pre className="overflow-auto rounded-md bg-zinc-900 p-4 text-sm text-zinc-200">
                {JSON.stringify(config.config, null, 2)}
              </pre>
            </CardContent>
          </Card>

          {/* Version History */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Version History</CardTitle>
            </CardHeader>
            <CardContent>
              {versions.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No version history yet. Versions are created when you activate a different configuration.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Version</TableHead>
                      <TableHead>Notes</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {versions.map((v) => (
                      <TableRow key={v.version}>
                        <TableCell>
                          <Badge variant="outline">v{v.version}</Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {v.notes ?? "-"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(v.created_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={activating !== null}
                            onClick={() => handleActivate(v.version)}
                          >
                            {activating === v.version ? "Activating..." : "Activate"}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Comparison View */}
          {versions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Compare Versions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="mb-4 flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-muted-foreground">Left:</label>
                    <select
                      value={diffLeft ?? ""}
                      onChange={(e) => setDiffLeft(e.target.value === "" ? null : Number(e.target.value))}
                      className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground"
                    >
                      <option value="">Select version</option>
                      <option value={0}>Current (v{config.version})</option>
                      {versions.map((v) => (
                        <option key={v.version} value={v.version}>
                          v{v.version}
                        </option>
                      ))}
                    </select>
                  </div>
                  <span className="text-muted-foreground">vs</span>
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-muted-foreground">Right:</label>
                    <select
                      value={diffRight ?? ""}
                      onChange={(e) => setDiffRight(e.target.value === "" ? null : Number(e.target.value))}
                      className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground"
                    >
                      <option value="">Select version</option>
                      <option value={0}>Current (v{config.version})</option>
                      {versions.map((v) => (
                        <option key={v.version} value={v.version}>
                          v{v.version}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {diffLeft !== null && diffRight !== null && diffEntries !== null ? (
                  diffEntries.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No differences found. The configurations are identical.
                    </p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Key</TableHead>
                          <TableHead>Left</TableHead>
                          <TableHead>Right</TableHead>
                          <TableHead>Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {diffEntries.map((d) => (
                          <TableRow key={d.key}>
                            <TableCell className="font-mono text-sm">{d.key}</TableCell>
                            <TableCell className="font-mono text-sm">
                              {d.left || <span className="text-muted-foreground">-</span>}
                            </TableCell>
                            <TableCell className="font-mono text-sm">
                              {d.right || <span className="text-muted-foreground">-</span>}
                            </TableCell>
                            <TableCell>
                              <Badge
                                className={
                                  d.status === "changed"
                                    ? "bg-yellow-900 text-yellow-200 hover:bg-yellow-900"
                                    : d.status === "added"
                                      ? "bg-green-900 text-green-200 hover:bg-green-900"
                                      : "bg-red-900 text-red-200 hover:bg-red-900"
                                }
                              >
                                {d.status}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Select two versions above to compare their configurations.
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
