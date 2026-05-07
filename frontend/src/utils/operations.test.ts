import { describe, expect, it } from "vitest";
import { formatNewsActionResult } from "./operations";

describe("formatNewsActionResult", () => {
  it("formats crawl-news results as human-readable text", () => {
    const result = formatNewsActionResult({
      action: "crawl-news",
      created_count: 1,
    });

    expect(result.title).toBe("最近一次操作结果");
    expect(result.lines).toEqual(["已抓取持仓新闻", "新增新闻 1 条"]);
  });
});
