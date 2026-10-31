import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { Tooltip } from "radix-ui";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { SessionProvider } from "./lib/session";
import { ApprovePage } from "./pages/ApprovePage";
import { DealCardPage } from "./pages/DealCardPage";
import { DesignSystemPage } from "./pages/DesignSystemPage";
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
                <Route path="/design" element={<DesignSystemPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
          </SessionProvider>
        </Tooltip.Provider>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
);
