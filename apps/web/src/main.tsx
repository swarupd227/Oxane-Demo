import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { Tooltip } from "radix-ui";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AgentsConsole } from "./agents/AgentsConsole";
import { AppShell } from "./components/shell/AppShell";
import { WorkspaceShell } from "./components/shell/WorkspaceShell";
import { PersonaProvider } from "./lib/persona";
import { ClientPage, ClientsPage } from "./pages/deals/ClientsPage";
import { DealCasePage } from "./pages/deals/DealCasePage";
import { FacilitiesPage, FacilityPage, SubmissionPage } from "./pages/deals/FacilityPages";
import { MyWorkPage } from "./pages/deals/MyWorkPage";
import { PortalPage } from "./pages/deals/PortalPage";
import { AiProviderPage } from "./pages/settings/AiProviderPage";
import { SessionProvider } from "./lib/session";
import { MonitoringShell } from "./monitoring/MonitoringShell";
import { CollateralPage } from "./monitoring/pages/CollateralPage";
import { CovenantsPage } from "./monitoring/pages/CovenantsPage";
import { CycleScorecardPage } from "./monitoring/pages/CycleScorecardPage";
import { MappingPage as CycleMappingPage } from "./monitoring/pages/MappingPage";
import { MonitorPage } from "./monitoring/pages/MonitorPage";
import { PackPage } from "./monitoring/pages/PackPage";
import { PortfolioPage } from "./monitoring/pages/PortfolioPage";
import { ReconciliationPage } from "./monitoring/pages/ReconciliationPage";
import { StatusCallPage } from "./monitoring/pages/StatusCallPage";
import { SubmissionsPage } from "./monitoring/pages/SubmissionsPage";
import { TermsTimelinePage } from "./monitoring/pages/TermsTimelinePage";
import { TriagePage } from "./monitoring/pages/TriagePage";
import { ValidationPage as CycleValidationPage } from "./monitoring/pages/ValidationPage";
import { ApprovePage } from "./pages/ApprovePage";
import { BackbookPage } from "./pages/BackbookPage";
import { CasesPage } from "./pages/CasesPage";
import { CaseSummaryPage } from "./pages/CaseSummaryPage";
import { ClientModelPage } from "./pages/ClientModelPage";
import { ConfigurationPage } from "./pages/ConfigurationPage";
import { DealCardPage } from "./pages/DealCardPage";
import { DefinitionsPage } from "./pages/DefinitionsPage";
import { ExceptionsPage } from "./pages/ExceptionsPage";
import { IntakePage } from "./pages/IntakePage";
import { MappingPage } from "./pages/MappingPage";
import { QcPage } from "./pages/QcPage";
import { QueriesPage } from "./pages/QueriesPage";
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
          <PersonaProvider>
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
                <Route path="/definitions" element={<DefinitionsPage />} />
                <Route path="/configuration" element={<ConfigurationPage />} />
                <Route path="/backbook" element={<BackbookPage />} />
                <Route path="/client-model" element={<ClientModelPage />} />
                <Route path="/queries" element={<QueriesPage />} />
                <Route path="/qc" element={<QcPage />} />
                <Route path="/cases" element={<CasesPage />} />
                <Route path="/cases/:number" element={<CaseSummaryPage />} />
                <Route path="/agents/*" element={<AgentsConsole />} />
              </Route>
              <Route element={<WorkspaceShell />}>
                <Route path="/work" element={<MyWorkPage />} />
                <Route path="/portal" element={<PortalPage />} />
                <Route path="/clients" element={<ClientsPage />} />
                <Route path="/clients/:id" element={<ClientPage />} />
                <Route path="/deals/cases/:id" element={<DealCasePage />} />
                <Route path="/deals/cases/:id/:tab" element={<DealCasePage />} />
                <Route path="/facilities" element={<FacilitiesPage />} />
                <Route path="/facilities/:id" element={<FacilityPage />} />
                <Route path="/facilities/:id/submissions/:sid" element={<SubmissionPage />} />
                <Route path="/settings" element={<Navigate to="/settings/ai-provider" replace />} />
                <Route path="/settings/ai-provider" element={<AiProviderPage />} />
              </Route>
              <Route path="/monitoring" element={<MonitoringShell />}>
                <Route index element={<PortfolioPage />} />
                <Route path="submissions" element={<SubmissionsPage />} />
                <Route path="mapping" element={<CycleMappingPage />} />
                <Route path="validation" element={<CycleValidationPage />} />
                <Route path="reconciliation" element={<ReconciliationPage />} />
                <Route path="terms" element={<TermsTimelinePage />} />
                <Route path="covenants" element={<CovenantsPage />} />
                <Route path="collateral" element={<CollateralPage />} />
                <Route path="triage" element={<TriagePage />} />
                <Route path="pack" element={<PackPage />} />
                <Route path="monitor" element={<MonitorPage />} />
                <Route path="status-call" element={<StatusCallPage />} />
                <Route path="results" element={<CycleScorecardPage />} />
                <Route path="agents/*" element={<AgentsConsole />} />
              </Route>
            </Routes>
          </BrowserRouter>
          </SessionProvider>
          </PersonaProvider>
        </Tooltip.Provider>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
);
