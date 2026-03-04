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
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  type UATSuite,
  type UATTestResult,
  type UATRunSummary,
} from "@/lib/api";

/* ---------- Helpers ---------- */

function StatusBadge({ status }: { status: string }) {
  if (status === "pass") {
    return (
      <Badge className="bg-green-900 text-green-200 hover:bg-green-900">
        PASS
      </Badge>
    );
  }
  if (status === "fail") {
    return <Badge variant="destructive">FAIL</Badge>;
  }
  return (
    <Badge className="bg-yellow-900 text-yellow-200 hover:bg-yellow-900">
      ERROR
    </Badge>
  );
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

/* ---------- Summary Bar ---------- */

function SummaryBar({
  summary,
  running,
}: {
  summary: UATRunSummary | null;
  running: boolean;
}) {
  if (running) {
    return (
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <span className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        Running tests...
      </div>
    );
  }
  if (!summary) return null;
  const allPassed = summary.failed === 0;
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <Badge
        className={
          allPassed
            ? "bg-green-900 text-green-200 hover:bg-green-900"
            : "bg-red-900 text-red-200 hover:bg-red-900"
        }
      >
        {summary.passed}/{summary.total} passed
      </Badge>
      {summary.failed > 0 && (
        <Badge variant="destructive">{summary.failed} failed</Badge>
      )}
      <span className="text-muted-foreground">
        {formatDuration(summary.duration_ms)}
      </span>
    </div>
  );
}

/* ---------- Test Result Row ---------- */

function TestResultRow({
  result,
  running,
  onRerun,
}: {
  result: UATTestResult;
  running: boolean;
  onRerun: (testId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <TableRow
        className="cursor-pointer select-none hover:bg-muted/40"
        onClick={() => setExpanded(!expanded)}
      >
        <TableCell className="font-mono text-xs">
          <span className="mr-1 inline-block w-3 text-muted-foreground">
            {expanded ? "\u25BE" : "\u25B8"}
          </span>
          {result.id}
        </TableCell>
        <TableCell>{result.name}</TableCell>
        <TableCell>
          <StatusBadge status={result.status} />
        </TableCell>
        <TableCell className="text-right font-mono text-xs">
          {formatDuration(result.duration_ms)}
        </TableCell>
        <TableCell className="text-right">
          <Button
            variant="ghost"
            size="xs"
            disabled={running}
            onClick={(e) => {
              e.stopPropagation();
              onRerun(result.id);
            }}
          >
            Re-run
          </Button>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={5} className="bg-muted/50 px-4 py-3">
            <div className="space-y-2 text-xs">
              <div>
                <span className="font-medium text-muted-foreground">Suite: </span>
                <span>{result.suite}</span>
                <span className="ml-4 font-medium text-muted-foreground">Status: </span>
                <StatusBadge status={result.status} />
                <span className="ml-4 font-medium text-muted-foreground">Duration: </span>
                <span className="font-mono">{formatDuration(result.duration_ms)}</span>
              </div>
              {result.details && (
                <div>
                  <span className="font-medium text-muted-foreground">Details:</span>
                  <pre className="mt-1 whitespace-pre-wrap rounded bg-muted p-2 text-foreground">
                    {result.details}
                  </pre>
                </div>
              )}
              {result.error && (
                <div>
                  <span className="font-medium text-destructive-foreground">Error:</span>
                  <pre className="mt-1 whitespace-pre-wrap rounded bg-destructive/10 p-2 text-destructive-foreground">
                    {result.error}
                  </pre>
                </div>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/* ---------- Suite Card ---------- */

function SuiteCard({
  suite,
  results,
  runningId,
  onRunSuite,
  onRerunTest,
}: {
  suite: UATSuite;
  results: UATTestResult[];
  runningId: string | null;
  onRunSuite: (suiteId: string) => void;
  onRerunTest: (testId: string) => void;
}) {
  const passed = results.filter((r) => r.status === "pass").length;
  const hasResults = results.length > 0;
  const isRunning = runningId === suite.id || runningId === "all";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-3">
          <CardTitle className="text-base">{suite.name}</CardTitle>
          <Badge variant="outline">{suite.test_count} tests</Badge>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={runningId !== null}
          onClick={() => onRunSuite(suite.id)}
        >
          {isRunning ? (
            <>
              <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
              Running...
            </>
          ) : (
            "Run Suite"
          )}
        </Button>
      </CardHeader>
      <CardContent>
        {isRunning && !hasResults && (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}
        {hasResults && (
          <>
            <div className="mb-3 text-xs text-muted-foreground">
              {passed}/{results.length} passed
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">ID</TableHead>
                  <TableHead>Test</TableHead>
                  <TableHead className="w-20">Status</TableHead>
                  <TableHead className="w-24 text-right">Duration</TableHead>
                  <TableHead className="w-20 text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((r) => (
                  <TestResultRow
                    key={r.id}
                    result={r}
                    running={runningId !== null}
                    onRerun={onRerunTest}
                  />
                ))}
              </TableBody>
            </Table>
          </>
        )}
        {!hasResults && !isRunning && (
          <p className="text-sm text-muted-foreground">
            Click "Run Suite" to execute tests.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------- Main Page ---------- */

export function UATPage() {
  const [suites, setSuites] = useState<UATSuite[]>([]);
  const [resultsBySuite, setResultsBySuite] = useState<
    Record<string, UATTestResult[]>
  >({});
  const [summary, setSummary] = useState<UATRunSummary | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingSuites, setLoadingSuites] = useState(true);

  // Load suites on mount
  useEffect(() => {
    api
      .uatSuites()
      .then((data) => {
        setSuites(data.suites);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load suites");
      })
      .finally(() => setLoadingSuites(false));
  }, []);

  // Group results by suite
  const applyResults = useCallback(
    (results: UATTestResult[], newSummary: UATRunSummary) => {
      setResultsBySuite((prev) => {
        const next = { ...prev };
        for (const r of results) {
          if (!next[r.suite]) next[r.suite] = [];
          // Replace existing result or add new
          const idx = next[r.suite].findIndex((x) => x.id === r.id);
          if (idx >= 0) {
            next[r.suite] = [...next[r.suite]];
            next[r.suite][idx] = r;
          } else {
            next[r.suite] = [...next[r.suite], r];
          }
        }
        return next;
      });
      setSummary(newSummary);
    },
    [],
  );

  const runAll = useCallback(async () => {
    setRunningId("all");
    setError(null);
    try {
      const data = await api.uatRun({});
      applyResults(data.results, data.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setRunningId(null);
    }
  }, [applyResults]);

  const runSuite = useCallback(
    async (suiteId: string) => {
      setRunningId(suiteId);
      setError(null);
      try {
        const data = await api.uatRun({ suite: suiteId });
        applyResults(data.results, data.summary);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Run failed");
      } finally {
        setRunningId(null);
      }
    },
    [applyResults],
  );

  const rerunTest = useCallback(
    async (testId: string) => {
      setRunningId(testId);
      setError(null);
      try {
        const data = await api.uatRun({ test_id: testId });
        applyResults(data.results, data.summary);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Re-run failed");
      } finally {
        setRunningId(null);
      }
    },
    [applyResults],
  );

  if (loadingSuites) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">UAT Runner</h1>
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  if (error && suites.length === 0) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">UAT Runner</h1>
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
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">UAT Runner</h1>
        <div className="flex items-center gap-4">
          <SummaryBar summary={summary} running={runningId === "all"} />
          <Button disabled={runningId !== null} onClick={runAll}>
            {runningId === "all" ? (
              <>
                <span className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Running All...
              </>
            ) : (
              "Run All"
            )}
          </Button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <Card className="mb-6 border-destructive">
          <CardContent className="py-3">
            <p className="text-sm text-destructive-foreground">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Suite cards */}
      <div className="space-y-6">
        {suites.map((suite) => (
          <SuiteCard
            key={suite.id}
            suite={suite}
            results={resultsBySuite[suite.id] ?? []}
            runningId={runningId}
            onRunSuite={runSuite}
            onRerunTest={rerunTest}
          />
        ))}
      </div>
    </div>
  );
}
