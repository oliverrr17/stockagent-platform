import { apiClient } from "./client";
import type { TradeCreatePayload, TradeIntentSnapshot, TradeRecord } from "../types";

export interface TradeListParams {
  market?: string;
  direction?: string;
  stock_code?: string;
  ordering?: string;
}

export async function fetchTrades(params: TradeListParams = {}) {
  const response = await apiClient.get<TradeRecord[]>("/api/trades/", { params });
  return response.data;
}

export async function createTrade(payload: TradeCreatePayload) {
  const response = await apiClient.post<TradeRecord>("/api/trades/", payload);
  return response.data;
}

export async function updateTradeIntentSnapshot(tradeId: number, intentSnapshot: TradeIntentSnapshot) {
  const response = await apiClient.patch<TradeRecord>(`/api/trades/${tradeId}/`, {
    intent_snapshot: intentSnapshot,
  });
  return response.data;
}
