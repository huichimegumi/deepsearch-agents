import {
  BranchesOutlined,
  BookOutlined,
  CheckCircleOutlined,
  BulbOutlined,
  LogoutOutlined
} from "@ant-design/icons";
import { Alert, App as AntApp, Button } from "antd";
import { useEffect, useRef, useState } from "react";
import { AuthPanel } from "./components/AuthPanel";
import { ChatComposer } from "./components/ChatComposer";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { ConversationThread } from "./components/ConversationThread";
import type { ChatTurn } from "./components/ConversationThread";
import { KnowledgeBaseDrawer } from "./components/KnowledgeBaseDrawer";
import { MemoryDrawer } from "./components/MemoryDrawer";
import { useAuth } from "./hooks/useAuth";
import { useConversationHistory } from "./hooks/useConversationHistory";
import { useDeepAgentSession } from "./hooks/useDeepAgentSession";
import type { MonitorMessage, OutputFile, UploadedItem } from "./types";

function createTurn(content: string): ChatTurn {
  return {
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`,
    content,
    events: [],
    files: [],
    isRunning: true,
    result: "",
    timestamp: new Date().toISOString()
  };
}

function toOutputFile(data: Record<string, unknown>): OutputFile | null {
  if (
    typeof data.name !== "string" ||
    typeof data.path !== "string" ||
    typeof data.size !== "number" ||
    typeof data.mtime !== "number"
  ) {
    return null;
  }

  return {
    name: data.name,
    path: data.path,
    size: data.size,
    mtime: data.mtime,
    type: typeof data.type === "string" ? data.type : "file"
  };
}

function getTurnFiles(events: MonitorMessage[]): OutputFile[] {
  const files = new Map<string, OutputFile>();
  events.forEach((event) => {
    if (event.event !== "file_created") {
      return;
    }
    const file = toOutputFile(event.data);
    if (file) {
      files.set(file.path, file);
    }
  });
  return Array.from(files.values()).sort((left, right) => right.mtime - left.mtime);
}

export default function App() {
  const { message } = AntApp.useApp();
  const [query, setQuery] = useState("");
  const [stagedItems, setStagedItems] = useState<UploadedItem[]>([]);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const streamRef = useRef<HTMLElement | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const wasRunningRef = useRef(false);
  const auth = useAuth();
  const history = useConversationHistory();
  const session = useDeepAgentSession(
    auth.token,
    history.activeThreadId,
    history.setActiveThreadId
  );

  useEffect(() => {
    setTurns((previous) => {
      if (previous.length === 0) {
        return previous;
      }

      const latestTurn = previous[previous.length - 1];
      const nextLatestTurn = {
        ...latestTurn,
        events: session.events,
        files: getTurnFiles(session.events),
        isRunning: session.isRunning,
        result: session.result
      };

      return [...previous.slice(0, -1), nextLatestTurn];
    });
  }, [session.events, session.isRunning, session.result]);

  useEffect(() => {
    const streamNode = streamRef.current;
    if (!streamNode || !shouldStickToBottomRef.current) {
      return;
    }

    window.requestAnimationFrame(() => {
      streamNode.scrollTo({
        top: streamNode.scrollHeight,
        behavior: "smooth"
      });
    });
  }, [turns]);

  useEffect(() => {
    if (!auth.isAuthenticated) {
      return;
    }

    history.refreshConversations()
      .then((items) => {
        if (items.some((item) => item.thread_id === history.activeThreadId)) {
          return history.loadConversationTurns(history.activeThreadId);
        }
        return [];
      })
      .then(setTurns)
      .catch((error: unknown) => {
        message.error(error instanceof Error ? error.message : "会话记录加载失败");
      });
  }, [auth.isAuthenticated]);

  useEffect(() => {
    if (wasRunningRef.current && !session.isRunning) {
      history.refreshConversations().catch(() => undefined);
    }
    wasRunningRef.current = session.isRunning;
  }, [history, session.isRunning]);

  function handleStreamScroll() {
    const streamNode = streamRef.current;
    if (!streamNode) {
      return;
    }
    const distanceToBottom =
      streamNode.scrollHeight - streamNode.scrollTop - streamNode.clientHeight;
    shouldStickToBottomRef.current = distanceToBottom < 80;
  }

  async function handleSubmit() {
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      message.warning("请输入研搜任务");
      return;
    }

    const nextTurn = createTurn(cleanQuery);
    shouldStickToBottomRef.current = true;
    setTurns((previous) => [...previous, nextTurn]);
    setQuery("");

    try {
      await session.submitTask(cleanQuery);
      history.refreshConversations().catch(() => undefined);
      message.success("任务已启动，执行过程会显示在对话中");
    } catch (error) {
      setTurns((previous) =>
        previous.map((turn) =>
          turn.id === nextTurn.id
            ? {
                ...turn,
                isRunning: false,
                result: error instanceof Error ? error.message : "任务启动失败"
              }
            : turn
        )
      );
      message.error(error instanceof Error ? error.message : "任务启动失败");
    }
  }

  async function handleCancel() {
    try {
      const response = await session.cancelCurrentTask();
      message.info(
        response.status === "cancelling"
          ? "取消请求已发送，正在等待当前调用结束"
          : "任务已取消"
      );
    } catch (error) {
      message.error(error instanceof Error ? error.message : "取消任务失败");
    }
  }

  async function handleUpload(items: UploadedItem[]) {
    try {
      const response = await session.uploadFiles(items);
      setStagedItems([]);
      message.success(`已上传 ${response.files.length} 个文件`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "上传失败");
    }
  }

  async function handleNewSession() {
    if (session.isRunning) {
      message.warning("当前任务仍在运行，请先取消或等待完成");
      return;
    }

    try {
      await history.startNewConversation();
      setTurns([]);
      setQuery("");
      setStagedItems([]);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "新建聊天失败");
    }
  }

  async function handleSelectConversation(threadId: string) {
    if (threadId === history.activeThreadId) {
      return;
    }
    if (session.isRunning) {
      message.warning("当前任务仍在运行，请先取消或等待完成");
      return;
    }

    try {
      const nextTurns = await history.loadConversationTurns(threadId);
      shouldStickToBottomRef.current = true;
      setTurns(nextTurns);
      setQuery("");
      setStagedItems([]);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "会话记录加载失败");
    }
  }

  async function handleDeleteConversation(threadId: string) {
    if (session.isRunning && threadId === history.activeThreadId) {
      message.warning("当前任务仍在运行，请先取消或等待完成");
      return;
    }

    try {
      await history.removeConversation(threadId);
      if (threadId === history.activeThreadId) {
        await history.startNewConversation();
        setTurns([]);
        setQuery("");
        setStagedItems([]);
      }
      message.success("聊天记录已删除");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "删除聊天记录失败");
    }
  }

  async function handleLogin(username: string, password: string) {
    try {
      await auth.signIn(username, password);
      message.success("登录成功");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "登录失败");
    }
  }

  async function handleRegister(username: string, password: string, displayName: string) {
    try {
      await auth.signUp(username, password, displayName);
      message.success("账号已创建");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "注册失败");
    }
  }

  function handleLogout() {
    auth.signOut();
    setTurns([]);
    setQuery("");
    setStagedItems([]);
    message.success("已退出登录");
  }

  if (!auth.isAuthenticated) {
    return (
      <AuthPanel
        isLoading={auth.isChecking}
        onLogin={handleLogin}
        onRegister={handleRegister}
      />
    );
  }

  return (
    <div className="chat-app-shell min-h-dvh">
      <aside className="chat-sidebar" aria-label="会话信息">
        <div className="sidebar-brand">
          <span className="panel-kicker">DEEPSEARCH</span>
          <h1>深度研搜</h1>
          <p>对话式多智能体研究台</p>
        </div>

        <ConversationSidebar
          activeThreadId={history.activeThreadId}
          conversations={history.conversations}
          isLoading={history.isLoadingHistory}
          onDeleteConversation={handleDeleteConversation}
          onNewChat={handleNewSession}
          onSelectConversation={handleSelectConversation}
        />

        <Button
          block
          className="knowledge-button"
          icon={<BookOutlined />}
          onClick={() => setKnowledgeOpen(true)}
        >
          知识库管理
        </Button>

        <Button
          block
          className="memory-button"
          icon={<BulbOutlined />}
          onClick={() => setMemoryOpen(true)}
        >
          长期记忆
        </Button>

        <div className="sidebar-section sidebar-user-section">
          <span className="sidebar-label">USER</span>
          <strong className="sidebar-user-name" title={auth.user?.username}>
            {auth.user?.display_name || auth.user?.username}
          </strong>
          <Button block icon={<LogoutOutlined />} onClick={handleLogout}>
            退出登录
          </Button>
        </div>
      </aside>

      <main className="chat-main">
        <header className="chat-topbar">
          <div>
            <span className="panel-kicker">CHAT WORKSPACE</span>
            <h2>深度研搜对话</h2>
          </div>
          <div className="topbar-actions">
            <div className="thread-mini" title={session.threadId}>
              <span>THREAD</span>
              <strong>{session.threadId.slice(0, 8)}</strong>
            </div>
            <div className={`run-indicator ${session.isRunning ? "run-indicator--live" : ""}`}>
              {session.isRunning ? <BranchesOutlined aria-hidden /> : <CheckCircleOutlined aria-hidden />}
              {session.isRunning ? "研搜中" : "待命"}
            </div>
            <Button
              className="mobile-knowledge-button"
              icon={<BookOutlined />}
              onClick={() => setKnowledgeOpen(true)}
            >
              知识库
            </Button>
            <Button
              className="mobile-memory-button"
              icon={<BulbOutlined />}
              onClick={() => setMemoryOpen(true)}
            >
              记忆
            </Button>
          </div>
        </header>

        {session.lastError ? (
          <Alert
            className="chat-alert"
            message={session.lastError}
            showIcon
            type="error"
          />
        ) : null}

        <section className="chat-stream-panel" onScroll={handleStreamScroll} ref={streamRef}>
          <ConversationThread
            onUseExample={setQuery}
            turns={turns}
          />
        </section>

        <ChatComposer
          isCancelling={session.isCancelling}
          isRunning={session.isRunning}
          isUploading={session.isUploading}
          onCancel={handleCancel}
          onNewSession={handleNewSession}
          onQueryChange={setQuery}
          onStagedItemsChange={setStagedItems}
          onSubmit={handleSubmit}
          onUpload={handleUpload}
          query={query}
          stagedItems={stagedItems}
          uploadedItems={session.uploadedItems}
        />
      </main>
      <KnowledgeBaseDrawer open={knowledgeOpen} onClose={() => setKnowledgeOpen(false)} />
      <MemoryDrawer open={memoryOpen} onClose={() => setMemoryOpen(false)} />
    </div>
  );
}
