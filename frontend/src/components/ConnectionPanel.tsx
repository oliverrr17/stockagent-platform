import { ApiOutlined, KeyOutlined, LoginOutlined } from "@ant-design/icons";
import { Button, Form, Input, Space, Typography, message } from "antd";
import axios from "axios";
import { useEffect, useState } from "react";
import { type ApiSettings } from "../api/client";
import { getApiErrorMessage } from "../utils/errors";

const { Text } = Typography;

type FormValues = ApiSettings & {
  username?: string;
  password?: string;
};

export function ConnectionPanel({
  settings,
  onSave,
  onAuthenticated,
}: {
  settings: ApiSettings;
  onSave: (next: ApiSettings) => void;
  onAuthenticated?: () => void;
}) {
  const [form] = Form.useForm<FormValues>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    form.setFieldsValue({
      baseUrl: settings.baseUrl || "",
      token: settings.token || "",
      refreshToken: settings.refreshToken || "",
    });
  }, [form, settings.baseUrl, settings.refreshToken, settings.token]);

  return (
    <Space direction="vertical" size={18} style={{ width: "100%" }}>
      <Text type="secondary">
        前端通过 JWT 调用后端接口。这里会同时保存访问令牌和刷新令牌；访问令牌过期后，
        前端会自动调用 `/api/auth/token/refresh/` 续期。
      </Text>
      <Form form={form} layout="vertical">
        <Form.Item label="接口基础地址" name="baseUrl">
          <Input placeholder="留空时使用本地 Vite 代理" prefix={<ApiOutlined />} />
        </Form.Item>
        <Form.Item label="访问令牌" name="token">
          <Input.TextArea rows={4} placeholder="JWT Access Token" />
        </Form.Item>
        <Form.Item label="刷新令牌" name="refreshToken">
          <Input.TextArea rows={4} placeholder="JWT Refresh Token（可选）" />
        </Form.Item>
        <Form.Item label="用户名" name="username">
          <Input placeholder="Django 用户名" prefix={<LoginOutlined />} />
        </Form.Item>
        <Form.Item label="密码" name="password">
          <Input.Password placeholder="Django 密码" prefix={<KeyOutlined />} />
        </Form.Item>
        <Space wrap>
          <Button
            type="primary"
            onClick={async () => {
              const values = await form.validateFields();
              onSave({
                baseUrl: values.baseUrl || "",
                token: values.token || "",
                refreshToken: values.refreshToken || "",
              });
              message.success("接口配置已保存。");
            }}
          >
            保存配置
          </Button>
          <Button
            loading={submitting}
            onClick={async () => {
              const values = await form.validateFields(["baseUrl", "username", "password"]);
              setSubmitting(true);
              try {
                const normalizedBase = (values.baseUrl || "").replace(/\/$/, "");
                const url = `${normalizedBase}/api/auth/token/`.replace(/^\/api/, "/api");
                const response = await axios.post(url, {
                  username: values.username,
                  password: values.password,
                });
                const nextToken = response.data.access as string;
                const nextRefreshToken = response.data.refresh as string;
                form.setFieldValue("token", nextToken);
                form.setFieldValue("refreshToken", nextRefreshToken);
                onSave({
                  baseUrl: values.baseUrl || "",
                  token: nextToken,
                  refreshToken: nextRefreshToken,
                });
                message.success("JWT 令牌获取成功，已启用自动续期。");
                onAuthenticated?.();
              } catch (error) {
                message.error(getApiErrorMessage(error, "令牌获取失败，请检查用户名、密码和接口地址。"));
              } finally {
                setSubmitting(false);
              }
            }}
          >
            登录并获取令牌
          </Button>
        </Space>
      </Form>
    </Space>
  );
}
