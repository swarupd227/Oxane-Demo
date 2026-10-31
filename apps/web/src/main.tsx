import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { Tooltip } from "radix-ui";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { scenes } from "./lib/scenes";
import { DealCardPage } from "./pages/DealCardPage";
import { DesignSystemPage } from "./pages/DesignSystemPage";
import { ScenePlaceholder } from "./pages/ScenePlaceholder";
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
          <BrowserRouter>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<DealCardPage />} />
                {scenes.slice(1).map((scene) => (
                  <Route key={scene.path} path={scene.path} element={<ScenePlaceholder />} />
                ))}
                <Route path="/design" element={<DesignSystemPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </Tooltip.Provider>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
);
