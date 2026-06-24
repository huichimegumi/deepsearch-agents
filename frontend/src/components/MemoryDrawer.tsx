import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined
} from "@ant-design/icons";
import {
  Button,
  Drawer,
  Empty,
  Input,
  List,
  Popconfirm,
  Select,
  Space,
  Tag,
  Tooltip
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { createMemory, deleteMemory, listMemories, searchMemories } from "../lib/api";
import type { UserMemory } from "../types";

interface MemoryDrawerProps {
  open: boolean;
  onClose: () => void;
}

const memoryTypeOptions = [
  { label: "偏好", value: "preference" },
  { label: "事实", value: "fact" },
  { label: "项目", value: "project" },
  { label: "指令", value: "instruction" },
  { label: "摘要", value: "summary" }
];

const memoryTypeLabels: Record<string, string> = {
  preference: "偏好",
  fact: "事实",
  project: "项目",
  instruction: "指令",
  summary: "摘要"
};

const memoryTypeColors: Record<string, string> = {
  preference: "cyan",
  fact: "blue",
  project: "green",
  instruction: "gold",
  summary: "purple"
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function MemoryDrawer({ open, onClose }: MemoryDrawerProps) {
  const [memories, setMemories] = useState<UserMemory[]>([]);
  const [content, setContent] = useState("");
  const [memoryType, setMemoryType] = useState("preference");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const groupedCount = useMemo(() => {
    return memories.reduce<Record<string, number>>((accumulator, item) => {
      accumulator[item.memory_type] = (accumulator[item.memory_type] || 0) + 1;
      return accumulator;
    }, {});
  }, [memories]);

  async function refreshMemories() {
    setMemories(await listMemories());
  }

  useEffect(() => {
    if (!open) return;
    void refreshMemories().catch((reason) =>
      setError(reason instanceof Error ? reason.message : String(reason))
    );
  }, [open]);

  async function handleCreate() {
    if (!content.trim()) return;
    setBusy(true);
    setError("");
    try {
      const item = await createMemory(content.trim(), memoryType);
      setMemories((current) => [item, ...current.filter((memory) => memory.id !== item.id)]);
      setContent("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存记忆失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSearch() {
    if (!query.trim()) {
      await refreshMemories();
      return;
    }
    setBusy(true);
    setError("");
    try {
      const hits = await searchMemories(query.trim(), 12);
      setMemories(hits);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "检索记忆失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(memoryId: string) {
    setBusy(true);
    setError("");
    try {
      await deleteMemory(memoryId);
      setMemories((current) => current.filter((item) => item.id !== memoryId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除记忆失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      className="memory-drawer"
      destroyOnClose={false}
      onClose={onClose}
      open={open}
      placement="right"
      title="长期记忆"
      width="min(680px, 100vw)"
    >
      <section className="memory-create-row">
        <Select
          options={memoryTypeOptions}
          onChange={setMemoryType}
          value={memoryType}
        />
        <Input.TextArea
          autoSize={{ minRows: 2, maxRows: 4 }}
          maxLength={4000}
          onChange={(event) => setContent(event.target.value)}
          placeholder="写入一条希望系统长期记住的偏好、项目背景或稳定事实"
          value={content}
        />
        <Tooltip title="保存记忆">
          <Button
            aria-label="保存记忆"
            disabled={!content.trim()}
            icon={<PlusOutlined />}
            loading={busy}
            onClick={handleCreate}
            type="primary"
          />
        </Tooltip>
      </section>

      <section className="memory-search-row">
        <Input
          allowClear
          onChange={(event) => setQuery(event.target.value)}
          onPressEnter={handleSearch}
          placeholder="搜索记忆"
          prefix={<SearchOutlined />}
          value={query}
        />
        <Tooltip title="搜索">
          <Button
            aria-label="搜索记忆"
            icon={<SearchOutlined />}
            loading={busy}
            onClick={handleSearch}
          />
        </Tooltip>
        <Tooltip title="刷新">
          <Button
            aria-label="刷新记忆"
            icon={<ReloadOutlined />}
            onClick={() => void refreshMemories()}
          />
        </Tooltip>
      </section>

      {error ? <div className="memory-error">{error}</div> : null}

      <div className="memory-stat-row">
        {memoryTypeOptions.map((item) => (
          <Tag key={item.value} color={memoryTypeColors[item.value]}>
            {item.label} {groupedCount[item.value] || 0}
          </Tag>
        ))}
      </div>

      <List
        dataSource={memories}
        locale={{ emptyText: <Empty description="还没有长期记忆" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        renderItem={(memory) => (
          <List.Item
            actions={[
              <Popconfirm
                key="delete"
                description="删除后不会再被 Agent 召回。"
                onConfirm={() => void handleDelete(memory.id)}
                title="删除这条记忆？"
              >
                <Button
                  aria-label={`删除记忆 ${memory.summary}`}
                  danger
                  icon={<DeleteOutlined />}
                  size="small"
                />
              </Popconfirm>
            ]}
            className="memory-row"
          >
            <List.Item.Meta
              description={
                <Space size="small" wrap>
                  <span>置信度 {(memory.confidence * 100).toFixed(0)}%</span>
                  <span>使用 {memory.access_count} 次</span>
                  <span>更新 {formatDate(memory.updated_at)}</span>
                </Space>
              }
              title={
                <Space align="start" wrap>
                  <Tag color={memoryTypeColors[memory.memory_type]}>
                    {memoryTypeLabels[memory.memory_type] || memory.memory_type}
                  </Tag>
                  <span className="memory-content">{memory.content}</span>
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </Drawer>
  );
}
