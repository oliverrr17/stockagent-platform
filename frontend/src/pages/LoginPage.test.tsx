import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

vi.mock("../components/ConnectionPanel", () => ({
  ConnectionPanel: () => <div>connection-panel</div>,
}));

describe("LoginPage", () => {
  it("renders login title and description", () => {
    render(
      <MemoryRouter>
        <LoginPage
          settings={{ baseUrl: "", token: "", refreshToken: "" }}
          onSave={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("登录")).toBeInTheDocument();
    expect(screen.getByText("登录后即可查看真实交易、持仓、新闻、通知与任务状态。")).toBeInTheDocument();
  });
});
