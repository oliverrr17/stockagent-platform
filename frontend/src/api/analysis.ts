import { apiClient } from "./client";
import type { ReviewReport } from "../types";

export async function generateReviewReport(tradeRecordId: number) {
  const response = await apiClient.post<ReviewReport>("/api/analysis/generate/", {
    trade_record_id: tradeRecordId,
  });
  return response.data;
}

export async function fetchReviewReports(tradeRecordId?: number) {
  const response = await apiClient.get<ReviewReport[]>("/api/analysis/", {
    params: tradeRecordId ? { trade_record: tradeRecordId } : {},
  });
  return response.data;
}
