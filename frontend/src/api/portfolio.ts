import { apiClient } from "./client";
import type {
  CashAccount,
  CashFlow,
  CashFlowPayload,
  PortfolioDailyContributionResponse,
  HKStockStats,
  PortfolioClearedPosition,
  PortfolioOverview,
  PortfolioPositionAnalytics,
  Position,
  PositionEntryPayload,
  TradeRecord,
} from "../types";

export async function fetchActivePositions() {
  const response = await apiClient.get<Position[]>("/api/portfolio/positions/active/");
  return response.data;
}

export async function fetchPortfolioDashboard() {
  const response = await apiClient.get<{
    positions: Position[];
    position_analytics: PortfolioPositionAnalytics[];
    overview: PortfolioOverview;
    cash_accounts: CashAccount[];
    cash_flows: CashFlow[];
  }>("/api/portfolio/analytics/dashboard/");
  return response.data;
}

export async function createManualPosition(payload: PositionEntryPayload) {
  const response = await apiClient.post<Position>("/api/portfolio/positions/manual_entry/", payload);
  return response.data;
}

export async function updatePosition(positionId: number, payload: Partial<PositionEntryPayload> & { quantity?: number }) {
  const response = await apiClient.patch<Position>(`/api/portfolio/positions/${positionId}/`, payload);
  return response.data;
}

export async function deletePosition(positionId: number) {
  await apiClient.delete(`/api/portfolio/positions/${positionId}/`);
}

export async function fetchHKStats(stockCode: string) {
  const response = await apiClient.get<HKStockStats>(`/api/portfolio/hk-stats/${stockCode}/`);
  return response.data;
}

export async function fetchHKTradeHistory(stockCode: string) {
  const response = await apiClient.get<TradeRecord[]>(`/api/portfolio/hk-stats/${stockCode}/trade_history/`);
  return response.data;
}

export async function fetchCashAccounts() {
  const response = await apiClient.get<CashAccount[]>("/api/portfolio/cash-accounts/");
  return response.data;
}

export async function fetchCashFlows() {
  const response = await apiClient.get<CashFlow[]>("/api/portfolio/cash-flows/");
  return response.data;
}

export async function createCashFlow(payload: CashFlowPayload) {
  const response = await apiClient.post<CashFlow>("/api/portfolio/cash-flows/", payload);
  return response.data;
}

export async function fetchPortfolioOverview() {
  const response = await apiClient.get<PortfolioOverview>("/api/portfolio/analytics/overview/");
  return response.data;
}

export async function fetchPortfolioDailyContributions(snapshotDate: string) {
  const response = await apiClient.get<PortfolioDailyContributionResponse>(`/api/portfolio/analytics/contributions/${snapshotDate}/`);
  return response.data;
}

export async function fetchPositionAnalytics() {
  const response = await apiClient.get<PortfolioPositionAnalytics[]>("/api/portfolio/analytics/positions/");
  return response.data;
}

export async function fetchPositionAnalyticsDetail(stockCode: string) {
  const response = await apiClient.get<PortfolioPositionAnalytics>(`/api/portfolio/analytics/positions/${stockCode}/`);
  return response.data;
}

export async function fetchClearedPositions() {
  const response = await apiClient.get<PortfolioClearedPosition[]>("/api/portfolio/analytics/cleared/");
  return response.data;
}
