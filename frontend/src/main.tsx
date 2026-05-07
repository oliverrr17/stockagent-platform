import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, theme } from "antd";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#116466",
          colorInfo: "#116466",
          colorSuccess: "#2d6a4f",
          colorWarning: "#ca8a04",
          colorError: "#b42318",
          borderRadius: 18,
          fontFamily: '"Aptos", "Bahnschrift", "Segoe UI", sans-serif',
          colorBgLayout: "#f4f0e8",
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
);
