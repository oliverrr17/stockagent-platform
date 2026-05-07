import { createContext, useContext } from "react";
import type { ApiSettings } from "../api/client";

export interface ApiSettingsContextValue {
  settings: ApiSettings;
  setSettings: (next: ApiSettings) => void;
}

export const ApiSettingsContext = createContext<ApiSettingsContextValue | null>(null);

export function useApiSettings() {
  const context = useContext(ApiSettingsContext);
  if (!context) {
    throw new Error("useApiSettings must be used inside ApiSettingsContext.Provider");
  }
  return context;
}
