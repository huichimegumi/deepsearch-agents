import { API_BASE_URL } from "./config";
import { getAuthToken } from "./auth";
import type {
  CancelTaskResponse,
  FileListResponse,
  IndexJob,
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeUploadResponse,
  TaskResponse,
  UploadResponse
} from "../types";

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(input, {
    ...init,
    headers
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : `HTTP ${response.status}`;
    throw new Error(message);
  }

  return payload as T;
}

export async function startTask(query: string, threadId: string): Promise<TaskResponse> {
  return requestJson<TaskResponse>(apiUrl("/api/task"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      query,
      thread_id: threadId
    })
  });
}

export async function cancelTask(threadId: string): Promise<CancelTaskResponse> {
  return requestJson<CancelTaskResponse>(apiUrl(`/api/task/${encodeURIComponent(threadId)}/cancel`), {
    method: "POST"
  });
}

export async function uploadSessionFiles(
  files: File[],
  threadId: string
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("thread_id", threadId);
  files.forEach((file) => formData.append("files", file));

  return requestJson<UploadResponse>(apiUrl("/api/upload"), {
    method: "POST",
    body: formData
  });
}

export async function listSessionFiles(path: string): Promise<FileListResponse> {
  const url = new URL(apiUrl("/api/files"));
  url.searchParams.set("path", path);
  return requestJson<FileListResponse>(url);
}

export function getDownloadUrl(path: string): string {
  const url = new URL(apiUrl("/api/download"));
  url.searchParams.set("path", path);
  return url.toString();
}

export function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  return requestJson<KnowledgeBase[]>(apiUrl("/api/knowledge-bases"));
}

export function createKnowledgeBase(name: string, description: string): Promise<KnowledgeBase> {
  return requestJson<KnowledgeBase>(apiUrl("/api/knowledge-bases"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description })
  });
}

export async function deleteKnowledgeBase(knowledgeBaseId: string): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`),
    { method: "DELETE", headers: { Authorization: `Bearer ${getAuthToken()}` } }
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

export function listKnowledgeDocuments(knowledgeBaseId: string): Promise<KnowledgeDocument[]> {
  return requestJson<KnowledgeDocument[]>(
    apiUrl(`/api/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents`)
  );
}

export async function uploadKnowledgeDocument(
  knowledgeBaseId: string,
  file: File
): Promise<KnowledgeUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<KnowledgeUploadResponse>(
    apiUrl(`/api/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents`),
    { method: "POST", body: formData }
  );
}

export function reindexKnowledgeDocument(documentId: string): Promise<IndexJob> {
  return requestJson<IndexJob>(
    apiUrl(`/api/knowledge-bases/documents/${encodeURIComponent(documentId)}/reindex`),
    { method: "POST" }
  );
}

export async function deleteKnowledgeDocument(documentId: string): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/knowledge-bases/documents/${encodeURIComponent(documentId)}`),
    { method: "DELETE", headers: { Authorization: `Bearer ${getAuthToken()}` } }
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}
