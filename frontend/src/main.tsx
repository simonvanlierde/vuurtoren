import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";
import { DisplayCurrencyProvider } from "./lib/displayCurrency";
import { I18nProvider } from "./lib/i18n";
import { applyTheme, watchSystemTheme } from "./lib/theme";
import { PyodideGate } from "./pyodide/PyodideGate";

const queryClient = new QueryClient();

applyTheme();
watchSystemTheme();

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("missing #root element");
createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <DisplayCurrencyProvider>
          <PyodideGate>
            <App />
          </PyodideGate>
        </DisplayCurrencyProvider>
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
);
