import type { OperationsActionResult } from "../types";

export interface FormattedOperationResult {
  title: string;
  lines: string[];
}

function toCount(value: unknown) {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
}

function toSuccess(value: unknown) {
  return Boolean(value);
}

export function formatNewsActionResult(result: OperationsActionResult): FormattedOperationResult {
  const action = String(result.action ?? "");

  if (action === "crawl-news") {
    return {
      title: "最近一次操作结果",
      lines: ["已抓取持仓新闻", `新增新闻 ${toCount(result.created_count)} 条`],
    };
  }

  if (action === "push-news") {
    return {
      title: "最近一次操作结果",
      lines: [
        "已处理即时通知推送",
        `处理 ${toCount(result.processed)} 条`,
        `成功 ${toCount(result.success)} 条`,
        `失败 ${toCount(result.failed)} 条`,
      ],
    };
  }

  if (action === "push-digest") {
    return {
      title: "最近一次操作结果",
      lines: [toSuccess(result.success) ? "摘要邮件已发送" : "没有可发送的摘要内容"],
    };
  }

  return {
    title: "最近一次操作结果",
    lines: ["操作已完成"],
  };
}
