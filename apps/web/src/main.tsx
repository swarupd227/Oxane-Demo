import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { Tooltip } from "radix-ui";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { SessionProvider } from "./lib/session";
import { MonitoringShell } from "./monitoring/MonitoringShell";
import { CollateralPage } from "./monitoring/pages/CollateralPage";
import { CovenantsPage } from "./monitoring/pages/CovenantsPage";
import { CycleScorecardPage } from "./monitoring/pages/CycleScorecardPage";
import { PackPage } from "./monitoring/pages/PackPage";
import { PortfolioPage } from "./monitoring/pages/PortfolioPage";
import { ReconciliationPage } from "./monitoring/pages/ReconciliationPage";
import { SubmissionsPage } from "./monitoring/pages/SubmissionsPage";
import { TermsTimelinePage } from "./monitoring/pages/TermsTimelinePage";
import { TriagePage } from "./monitoring/pages/TriagePage";
import { ApprovePage } from "./pages/ApprovePage";
import { DealCardPage } from "./pages/DealCardPage";
import { ExceptionsPage } from "./pages/ExceptionsPage";
import { IntakePage } from "./pages/IntakePage";
import { MappingPage } from "./pages/MappingPage";
import { RulesPage } from "./pages/RulesPage";
import { ScorecardPage } from "./pages/ScorecardPage";
import { TermsPage } from "./pages/TermsPage";
import { ValidationPage } from "./pages/ValidationPage";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, retryDelay: 300, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <Tooltip.Provider delayDuration={200}>
          <SessionProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<DealCardPage />} />
                <Route path="/intake" element={<IntakePage />} />
                <Route path="/terms" element={<TermsPage />} />
                <Route path="/rules" element={<RulesPage />} />
                <Route path="/mapping" element={<MappingPage />} />
                <Route path="/validation" element={<ValidationPage />} />
                <Route path="/exceptions" element={<ExceptionsPage />} />
                <Route path="/approve" element={<ApprovePage />} />
                <Route path="/results" element={<ScorecardPage />} />
              </Route>
              <Route path="/monitoring" element={<MonitoringShell />}>
                <Route index element={<PortfolioPage />} />
                <Route path="submissions" element={<SubmissionsPage />} />
                <Route path="reconciliation" element={<ReconciliationPage />} />
                <Route path="terms" element={<TermsTimelinePage />} />
                <Route path="covenants" element={<CovenantsPage />} />
                <Route path="collateral" element={<CollateralPage />} />
                <Route path="triage" element={<TriagePage />} />
                <Route path="pack" element={<PackPage />} />
                <Route path="results" element={<CycleScorecardPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
          </SessionProvider>
        </Tooltip.Provider>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
);
