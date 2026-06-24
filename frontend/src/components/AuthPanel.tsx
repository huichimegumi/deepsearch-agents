import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Form, Input } from "antd";
import { useState } from "react";

type AuthMode = "login" | "register";

interface AuthPanelProps {
  isLoading?: boolean;
  onLogin: (username: string, password: string) => Promise<void>;
  onRegister: (username: string, password: string, displayName: string) => Promise<void>;
}

interface AuthFormValues {
  username: string;
  password: string;
  displayName?: string;
}

export function AuthPanel({ isLoading, onLogin, onRegister }: AuthPanelProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<AuthFormValues>();

  async function handleFinish(values: AuthFormValues) {
    setSubmitting(true);
    try {
      if (mode === "login") {
        await onLogin(values.username, values.password);
      } else {
        await onRegister(values.username, values.password, values.displayName || "");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode);
    form.resetFields();
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="auth-brand">
          <span className="panel-kicker">DEEPSEARCH</span>
          <h1>登录 DeepSearch</h1>
          <p>使用用户名进入你的研搜工作区。</p>
        </div>

        <div className="auth-switch" role="tablist" aria-label="认证方式">
          <Button
            type={mode === "login" ? "primary" : "default"}
            onClick={() => switchMode("login")}
          >
            登录
          </Button>
          <Button
            type={mode === "register" ? "primary" : "default"}
            onClick={() => switchMode("register")}
          >
            注册
          </Button>
        </div>

        <Form form={form} layout="vertical" onFinish={handleFinish} requiredMark={false}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[
              { required: true, message: "请输入用户名" },
              { min: 3, message: "用户名至少 3 个字符" },
              {
                pattern: /^[A-Za-z0-9_.-]+$/,
                message: "仅支持字母、数字、下划线、点和短横线"
              }
            ]}
          >
            <Input autoComplete="username" prefix={<UserOutlined />} />
          </Form.Item>

          {mode === "register" ? (
            <Form.Item label="显示名称" name="displayName">
              <Input autoComplete="name" />
            </Form.Item>
          ) : null}

          <Form.Item
            label="密码"
            name="password"
            rules={[
              { required: true, message: "请输入密码" },
              { min: mode === "register" ? 8 : 1, message: "密码至少 8 个字符" }
            ]}
          >
            <Input.Password
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              prefix={<LockOutlined />}
            />
          </Form.Item>

          <Button
            block
            htmlType="submit"
            loading={submitting || isLoading}
            size="large"
            type="primary"
          >
            {mode === "login" ? "登录" : "创建账号"}
          </Button>
        </Form>
      </section>
    </main>
  );
}
