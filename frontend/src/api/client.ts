import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";

export interface ApiSettings {
  baseUrl: string;
  token: string;
  refreshToken: string;
}

const STORAGE_KEY = "stockagent.api.settings";
const AUTH_EVENT = "stockagent:auth-state-changed";

type AuthEventReason = "updated" | "cleared" | "expired";
type RetryableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

let refreshPromise: Promise<string | null> | null = null;

function dispatchAuthEvent(reason: AuthEventReason) {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new CustomEvent(AUTH_EVENT, { detail: { reason } }));
}

function authUrl(path: string, baseUrl: string) {
  const normalizedBase = baseUrl.replace(/\/$/, "");
  return `${normalizedBase}${path}`.replace(/^\/api/, "/api");
}

export function getApiSettings(): ApiSettings {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return {
      baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
      token: "",
      refreshToken: "",
    };
  }

  try {
    const parsed = JSON.parse(raw) as Partial<ApiSettings>;
    return {
      baseUrl: parsed.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? "",
      token: parsed.token ?? "",
      refreshToken: parsed.refreshToken ?? "",
    };
  } catch {
    return {
      baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
      token: "",
      refreshToken: "",
    };
  }
}

export function saveApiSettings(settings: ApiSettings) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  dispatchAuthEvent("updated");
}

export function clearApiSettings(reason: AuthEventReason = "cleared") {
  const next: ApiSettings = {
    baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
    token: "",
    refreshToken: "",
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  dispatchAuthEvent(reason);
}

export function getAuthEventName() {
  return AUTH_EVENT;
}

function isAuthRequest(url?: string) {
  return Boolean(url?.includes("/api/auth/token/"));
}

async function refreshAccessToken() {
  const settings = getApiSettings();
  if (!settings.refreshToken) {
    return null;
  }

  const response = await axios.post<{ access: string; refresh?: string }>(
    authUrl("/api/auth/token/refresh/", settings.baseUrl),
    {
      refresh: settings.refreshToken,
    },
    {
      headers: {
        "Content-Type": "application/json",
      },
    },
  );

  const next: ApiSettings = {
    ...settings,
    token: response.data.access,
    refreshToken: response.data.refresh ?? settings.refreshToken,
  };
  saveApiSettings(next);
  return next.token;
}

export const apiClient = axios.create({
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const settings = getApiSettings();
  const baseUrl = settings.baseUrl.replace(/\/$/, "");
  config.baseURL = baseUrl || "";
  if (settings.token) {
    config.headers.Authorization = `Bearer ${settings.token}`;
  } else {
    delete config.headers.Authorization;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const response = error.response;
    const originalRequest = error.config as RetryableConfig | undefined;

    if (
      !response ||
      response.status !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      isAuthRequest(originalRequest.url)
    ) {
      return Promise.reject(error);
    }

    const settings = getApiSettings();
    if (!settings.refreshToken) {
      clearApiSettings("expired");
      return Promise.reject(error);
    }

    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }

      const nextToken = await refreshPromise;
      if (!nextToken) {
        clearApiSettings("expired");
        return Promise.reject(error);
      }

      originalRequest._retry = true;
      originalRequest.headers = originalRequest.headers ?? {};
      originalRequest.headers.Authorization = `Bearer ${nextToken}`;

      return apiClient(originalRequest);
    } catch (refreshError) {
      clearApiSettings("expired");
      return Promise.reject(refreshError);
    }
  },
);
