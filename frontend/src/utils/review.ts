export interface ReviewMetricEntry {
  label: string;
  display: string;
}

function formatMetricLabel(key: string) {
  return key.replace(/_/g, " ");
}

function isChartCollection(value: unknown) {
  return Array.isArray(value) && value.some((item) => item !== null && typeof item === "object");
}

function formatMetricValue(value: unknown) {
  if (typeof value === "number") {
    return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

export function extractReviewMetricEntries(data: Record<string, unknown>): ReviewMetricEntry[] {
  return Object.entries(data)
    .filter(([_, value]) => !isChartCollection(value))
    .map(([key, value]) => ({
      label: formatMetricLabel(key),
      display: formatMetricValue(value),
    }));
}
