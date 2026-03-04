import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AdminPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Admin</h1>
      <Card>
        <CardHeader>
          <CardTitle>Admin Panels</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Feature Explorer, Signal Inspector, Regime Monitor, and Model
            Dashboard will be available after T-404 is completed.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
