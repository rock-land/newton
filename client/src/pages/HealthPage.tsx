import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type HealthResponse } from "@/lib/api";

function StatusBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <Badge className="bg-green-900 text-green-200 hover:bg-green-900">OK</Badge>
  ) : (
    <Badge variant="destructive">DOWN</Badge>
  );
}

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

function AgeBadge({ seconds }: { seconds: number | null }) {
  if (seconds === null) {
    return <Badge variant="outline">N/A</Badge>;
  }
  if (seconds < 7200) {
    return <Badge className="bg-green-900 text-green-200 hover:bg-green-900">{formatAge(seconds)}</Badge>;
  }
  if (seconds < 14400) {
    return <Badge className="bg-yellow-900 text-yellow-200 hover:bg-yellow-900">{formatAge(seconds)}</Badge>;
  }
  return <Badge variant="destructive">{formatAge(seconds)}</Badge>;
}

const POLL_INTERVAL_MS = 10_000;

export function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const data = await api.health();
      setHealth(data);
      setError(null);
      setLastFetch(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch health");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchHealth]);

  if (loading) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">System Health</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error && !health) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">System Health</h1>
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive-foreground">{error}</p>
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
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">System Health</h1>
        {lastFetch && (
          <span className="text-xs text-muted-foreground">
            Last updated: {lastFetch.toLocaleTimeString()}
            {error && <span className="ml-2 text-destructive-foreground">(stale)</span>}
          </span>
        )}
      </div>

      {/* Quick Status Cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              API Status
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
              Generated
            </CardTitle>
          </CardHeader>
          <CardContent>
            <span className="font-mono text-lg">
              {health?.generated_at
                ? new Date(health.generated_at).toLocaleTimeString()
                : "-"}
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Brokers */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Brokers</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Broker</TableHead>
                <TableHead>Connected</TableHead>
                <TableHead>Latency (ms)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {health ? (
                Object.entries(health.brokers).map(([name, b]) => (
                  <TableRow key={name}>
                    <TableCell className="font-medium capitalize">{name}</TableCell>
                    <TableCell>
                      <StatusBadge ok={b.connected} />
                    </TableCell>
                    <TableCell>
                      {b.last_response_ms !== null ? `${b.last_response_ms}ms` : "-"}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={3} className="text-muted-foreground">
                    Loading...
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Instruments */}
      <Card>
        <CardHeader>
          <CardTitle>Instruments</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Instrument</TableHead>
                <TableHead>Last Candle Age</TableHead>
                <TableHead>Reconciliation</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {health ? (
                Object.entries(health.instruments).map(([name, inst]) => (
                  <TableRow key={name}>
                    <TableCell className="font-medium font-mono">
                      {name}
                    </TableCell>
                    <TableCell>
                      <AgeBadge seconds={inst.last_candle_age_seconds} />
                    </TableCell>
                    <TableCell>
                      {inst.reconciled ? "OK" : "Pending"}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={3} className="text-muted-foreground">
                    Loading...
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
