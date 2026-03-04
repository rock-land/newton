import { BrowserRouter, Routes, Route } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Layout } from "@/components/layout/Layout";
import { HealthPage } from "@/pages/HealthPage";
import { UATPage } from "@/pages/UATPage";
import { AdminPage } from "@/pages/AdminPage";

export default function App() {
  return (
    <BrowserRouter>
      <TooltipProvider>
        <ErrorBoundary>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<HealthPage />} />
              <Route path="uat" element={<UATPage />} />
              <Route path="admin" element={<AdminPage />} />
            </Route>
          </Routes>
        </ErrorBoundary>
      </TooltipProvider>
    </BrowserRouter>
  );
}
