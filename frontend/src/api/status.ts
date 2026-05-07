import { apiClient } from "./client";
import type { OperationsActionResult, OperationsStatus } from "../types";

export async function fetchOperationsStatus() {
  const response = await apiClient.get<OperationsStatus>("/api/status/operations/");
  return response.data;
}

export async function runOperation(action: string, payload: Record<string, unknown> = {}) {
  const response = await apiClient.post<OperationsActionResult>(`/api/status/actions/${action}/`, payload);
  return response.data;
}
