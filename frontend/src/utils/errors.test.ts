import axios from "axios";
import { describe, expect, it } from "vitest";
import { getApiErrorMessage } from "./errors";

describe("getApiErrorMessage", () => {
  it("returns backend detail when available", () => {
    const error = new axios.AxiosError(
      "Request failed",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      {
        data: { detail: "Invalid HK-stock code: BAD" },
        status: 400,
        statusText: "Bad Request",
        headers: {},
        config: {} as never,
      },
    );

    expect(getApiErrorMessage(error, "fallback")).toBe("Invalid HK-stock code: BAD");
  });

  it("returns auth-expired message for 401", () => {
    const error = new axios.AxiosError(
      "Unauthorized",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      {
        data: {},
        status: 401,
        statusText: "Unauthorized",
        headers: {},
        config: {} as never,
      },
    );

    expect(getApiErrorMessage(error, "fallback")).toBe("登录状态已失效，请重新登录。");
  });

  it("falls back when backend returns an HTML error page", () => {
    const error = new axios.AxiosError(
      "Request failed",
      "ERR_BAD_RESPONSE",
      undefined,
      undefined,
      {
        data: "<!DOCTYPE html><html><body>OperationalError: no such table</body></html>",
        status: 500,
        statusText: "Internal Server Error",
        headers: {},
        config: {} as never,
      },
    );

    expect(getApiErrorMessage(error, "fallback")).toBe("fallback");
  });
});
