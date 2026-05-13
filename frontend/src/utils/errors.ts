import axios from "axios";

function isHtmlDocument(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return normalized.startsWith("<!doctype html") || normalized.startsWith("<html");
}

function isAuthTokenRequest(url?: string): boolean {
  return Boolean(url?.includes("/api/auth/token/"));
}

function firstErrorValue(value: unknown): string | null {
  if (!value) {
    return null;
  }

  if (typeof value === "string") {
    return isHtmlDocument(value) ? null : value;
  }

  if (Array.isArray(value)) {
    const first = value.find((item) => typeof item === "string");
    return typeof first === "string" ? firstErrorValue(first) : null;
  }

  if (typeof value === "object") {
    for (const entry of Object.values(value as Record<string, unknown>)) {
      const nested = firstErrorValue(entry);
      if (nested) {
        return nested;
      }
    }
  }

  return null;
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    if (error.code === "ERR_NETWORK") {
      return "无法连接到后端接口，请检查本地服务是否已启动。";
    }

    if (error.response?.status === 401) {
      if (isAuthTokenRequest(error.config?.url)) {
        return "用户名或密码错误，或当前本地后端没有可用账号。";
      }
      return "登录状态已失效，请重新登录。";
    }

    if (typeof error.response?.data === "string" && isHtmlDocument(error.response.data)) {
      return fallback;
    }

    const detail = firstErrorValue(error.response?.data);
    if (detail) {
      return detail;
    }

    if (error.message) {
      return error.message;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}
