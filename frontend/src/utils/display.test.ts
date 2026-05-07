import { describe, expect, it } from "vitest";
import {
  directionMeta,
  marketMeta,
  notificationStatusMeta,
  positionOriginMeta,
  priorityMeta,
  sourceLabel,
} from "./display";

describe("display helpers", () => {
  it("maps trade direction metadata", () => {
    expect(directionMeta("BUY").color).toBe("green");
    expect(directionMeta("SELL").color).toBe("volcano");
    expect(directionMeta("BUY").label).not.toBe("BUY");
    expect(directionMeta("SELL").label).not.toBe("SELL");
  });

  it("maps market and origin metadata", () => {
    expect(marketMeta("HK_STOCK").color).toBe("gold");
    expect(positionOriginMeta("MANUAL").color).toBe("processing");
    expect(marketMeta("HK_STOCK").label).not.toBe("HK_STOCK");
    expect(positionOriginMeta("MANUAL").label).not.toBe("MANUAL");
  });

  it("maps notification and priority metadata", () => {
    expect(notificationStatusMeta("FAILED").color).toBe("red");
    expect(priorityMeta("P2").color).toBe("orange");
  });

  it("maps manual trade source label", () => {
    expect(sourceLabel("MANUAL")).not.toBe("MANUAL");
  });
});
