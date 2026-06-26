import "antd/dist/reset.css";
import { App as AntApp, ConfigProvider, theme } from "antd";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#0b628d",
          colorSuccess: "#16834a",
          colorWarning: "#b7791f",
          colorError: "#d9365d",
          colorInfo: "#3850b8",
          colorBgBase: "#e9eef4",
          colorBgContainer: "#f4f7fa",
          colorBorder: "rgba(36, 72, 96, 0.22)",
          borderRadius: 8,
          fontFamily:
            "'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif",
          fontFamilyCode:
            "'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace"
        },
        components: {
          Button: {
            controlHeightLG: 46,
            primaryShadow: "0 10px 28px rgba(11, 98, 141, 0.18)"
          },
          Input: {
            activeBorderColor: "#0b628d",
            hoverBorderColor: "#16834a"
          }
        }
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
