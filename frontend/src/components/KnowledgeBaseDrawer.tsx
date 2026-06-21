import {
  DeleteOutlined,
  FileSearchOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined
} from "@ant-design/icons";
import {
  Button,
  Drawer,
  Empty,
  Input,
  List,
  Popconfirm,
  Progress,
  Select,
  Space,
  Tag,
  Tooltip,
  Upload
} from "antd";
import { useEffect, useMemo, useState } from "react";
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  deleteKnowledgeDocument,
  listKnowledgeBases,
  listKnowledgeDocuments,
  reindexKnowledgeDocument,
  uploadKnowledgeDocument
} from "../lib/api";
import type { KnowledgeBase, KnowledgeDocument } from "../types";

interface KnowledgeBaseDrawerProps {
  open: boolean;
  onClose: () => void;
}

const statusLabels: Record<string, string> = {
  pending: "等待索引",
  indexing: "索引中",
  ready: "可检索",
  failed: "失败"
};

const statusColors: Record<string, string> = {
  pending: "gold",
  indexing: "processing",
  ready: "success",
  failed: "error"
};

function formatBytes(size: number): string {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function KnowledgeBaseDrawer({ open, onClose }: KnowledgeBaseDrawerProps) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => knowledgeBases.find((item) => item.id === selectedId),
    [knowledgeBases, selectedId]
  );

  async function refreshKnowledgeBases() {
    const rows = await listKnowledgeBases();
    setKnowledgeBases(rows);
    setSelectedId((current) => current || rows[0]?.id);
  }

  async function refreshDocuments(id = selectedId) {
    if (!id) {
      setDocuments([]);
      return;
    }
    setDocuments(await listKnowledgeDocuments(id));
  }

  useEffect(() => {
    if (!open) return;
    void refreshKnowledgeBases().catch((reason) => setError(String(reason)));
  }, [open]);

  useEffect(() => {
    if (!open || !selectedId) return;
    void refreshDocuments(selectedId).catch((reason) => setError(String(reason)));
    const timer = window.setInterval(() => {
      void refreshDocuments(selectedId).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [open, selectedId]);

  async function handleCreate() {
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const item = await createKnowledgeBase(name.trim(), description.trim());
      setKnowledgeBases((current) => [item, ...current]);
      setSelectedId(item.id);
      setName("");
      setDescription("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建知识库失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(file: File) {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      await uploadKnowledgeDocument(selectedId, file);
      await Promise.all([refreshDocuments(selectedId), refreshKnowledgeBases()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传入库失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      className="knowledge-drawer"
      destroyOnClose={false}
      onClose={onClose}
      open={open}
      placement="right"
      title="本地知识库"
      width="min(736px, 100vw)"
    >
      <section className="knowledge-create-row">
        <Input
          maxLength={160}
          onChange={(event) => setName(event.target.value)}
          placeholder="知识库名称"
          value={name}
        />
        <Input
          maxLength={4000}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="用途描述"
          value={description}
        />
        <Tooltip title="创建知识库">
          <Button
            aria-label="创建知识库"
            disabled={!name.trim()}
            icon={<PlusOutlined />}
            loading={busy}
            onClick={handleCreate}
            type="primary"
          />
        </Tooltip>
      </section>

      {error ? <div className="knowledge-error">{error}</div> : null}

      <div className="knowledge-toolbar">
        <Select
          options={knowledgeBases.map((item) => ({
            label: `${item.name} (${item.document_count})`,
            value: item.id
          }))}
          onChange={setSelectedId}
          placeholder="选择知识库"
          value={selectedId}
        />
        <Upload
          accept=".pdf,.docx,.md,.txt"
          beforeUpload={(file) => {
            void handleUpload(file);
            return false;
          }}
          disabled={!selectedId || busy}
          showUploadList={false}
        >
          <Button icon={<UploadOutlined />} loading={busy}>上传入库</Button>
        </Upload>
        <Tooltip title="刷新文档状态">
          <Button
            aria-label="刷新文档状态"
            icon={<ReloadOutlined />}
            onClick={() => void refreshDocuments()}
          />
        </Tooltip>
        <Popconfirm
          description="其中的原始文件和全部检索索引都会删除。"
          disabled={!selectedId}
          onConfirm={() => {
            if (!selectedId) return;
            void deleteKnowledgeBase(selectedId).then(async () => {
              setSelectedId(undefined);
              setDocuments([]);
              await refreshKnowledgeBases();
            });
          }}
          title="删除当前知识库？"
        >
          <Button
            aria-label="删除当前知识库"
            danger
            disabled={!selectedId}
            icon={<DeleteOutlined />}
          />
        </Popconfirm>
      </div>

      {selected ? <p className="knowledge-description">{selected.description || "暂无描述"}</p> : null}

      <List
        dataSource={documents}
        locale={{ emptyText: <Empty description="尚未上传文档" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        renderItem={(document) => (
          <List.Item
            actions={[
              <Tooltip key="reindex" title="重新索引">
                <Button
                  aria-label={`重新索引 ${document.filename}`}
                  icon={<FileSearchOutlined />}
                  onClick={() => void reindexKnowledgeDocument(document.id).then(() => refreshDocuments())}
                  size="small"
                />
              </Tooltip>,
              <Popconfirm
                key="delete"
                description="原始文件和检索索引都会删除。"
                onConfirm={() => void deleteKnowledgeDocument(document.id).then(() => refreshDocuments())}
                title="删除这份文档？"
              >
                <Button
                  aria-label={`删除 ${document.filename}`}
                  danger
                  icon={<DeleteOutlined />}
                  size="small"
                />
              </Popconfirm>
            ]}
            className="knowledge-document-row"
          >
            <List.Item.Meta
              description={
                <Space size="small" wrap>
                  <span>{formatBytes(document.size_bytes)}</span>
                  <span>{document.chunk_count} 个片段</span>
                  {document.error_message ? <span className="knowledge-error">{document.error_message}</span> : null}
                </Space>
              }
              title={
                <Space wrap>
                  <span>{document.filename}</span>
                  <Tag color={statusColors[document.status]}>{statusLabels[document.status] || document.status}</Tag>
                </Space>
              }
            />
            {document.status === "indexing" || document.status === "pending" ? (
              <Progress percent={document.status === "indexing" ? 60 : 10} size="small" status="active" />
            ) : null}
          </List.Item>
        )}
      />
    </Drawer>
  );
}
