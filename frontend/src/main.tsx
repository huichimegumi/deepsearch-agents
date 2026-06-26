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
          colorPrimary: "#0f7fb3",
          colorSuccess: "#16834a",
          colorWarning: "#b7791f",
          colorError: "#d9365d",
          colorInfo: "#4662d6",
          colorBgBase: "#f6f9fc",
          colorBgContainer: "#ffffff",
          colorBorder: "rgba(15, 82, 112, 0.18)",
          borderRadius: 8,
          fontFamily:
            "'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif",
          fontFamilyCode:
            "'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace"
        },
        components: {
          Button: {
            controlHeightLG: 46,
            primaryShadow: "0 10px 28px rgba(15, 127, 179, 0.18)"
          },
          Input: {
            activeBorderColor: "#0f7fb3",
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
