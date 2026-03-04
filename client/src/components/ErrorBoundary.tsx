import { Component, type ErrorInfo, type ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-destructive-foreground">
                Something went wrong
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-2 font-mono text-sm">
                {this.state.error.message}
              </p>
              <button
                className="text-sm text-muted-foreground underline"
                onClick={() => this.setState({ error: null })}
              >
                Try again
              </button>
            </CardContent>
          </Card>
        </div>
      );
    }
    return this.props.children;
  }
}
