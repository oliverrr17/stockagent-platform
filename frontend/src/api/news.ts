import { apiClient } from "./client";
import type { NewsItem, NotificationLog } from "../types";

export interface NewsListParams {
  stock_code?: string;
  category?: string;
  source?: string;
  pushed?: boolean;
  query?: string;
  ordering?: string;
}

export async function fetchNews(params: NewsListParams = {}) {
  const response = await apiClient.get<NewsItem[]>("/api/news/", { params });
  return response.data;
}

export interface NotificationLogParams {
  stock_code?: string;
  status?: string;
  channel?: string;
  ordering?: string;
}

export async function fetchNotificationLogs(params: NotificationLogParams = {}) {
  const response = await apiClient.get<NotificationLog[]>("/api/news/notifications/", { params });
  return response.data;
}
