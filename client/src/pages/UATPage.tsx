import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function UATPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">UAT Runner</h1>
      <Card>
        <CardHeader>
          <CardTitle>Test Suites</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            UAT test runner will be available after T-402 and T-403 are
            completed.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
