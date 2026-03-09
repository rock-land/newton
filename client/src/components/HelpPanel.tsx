import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { HelpCircle, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { api } from "@/lib/api";

/** Map route paths to help section names. */
const ROUTE_TO_SECTION: Record<string, string> = {
  "/": "dashboard",
  "/health": "dashboard",
  "/strategy": "strategy",
  "/trading": "trading",
  "/config": "config",
  "/data": "data",
  "/backtest": "backtest",
  "/admin": "index",
  "/uat": "index",
};

export function HelpPanel() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const section = ROUTE_TO_SECTION[location.pathname] ?? "index";

  const loadHelp = useCallback(async (sec: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.helpContent(sec);
      setTitle(data.title);
      setContent(data.content);
    } catch {
      setError("Failed to load help content.");
      setTitle("Help");
      setContent("");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadHelp(section);
    }
  }, [open, section, loadHelp]);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" title="Help">
          <HelpCircle className="size-4" />
        </Button>
      </SheetTrigger>
      <SheetContent className="overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{loading ? "Loading..." : title || "Help"}</SheetTitle>
        </SheetHeader>
        <div className="mt-4 px-1">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          )}
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          {!loading && !error && content && (
            <div className="prose prose-sm prose-invert max-w-none">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
