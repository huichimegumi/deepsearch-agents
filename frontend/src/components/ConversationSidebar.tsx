import { DeleteOutlined, MessageOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Empty, Popconfirm, Spin, Tooltip } from "antd";
import type { ChatConversationRecord } from "../types";

interface ConversationSidebarProps {
  activeThreadId: string;
  conversations: ChatConversationRecord[];
  isLoading: boolean;
  onDeleteConversation: (threadId: string) => void;
  onNewChat: () => void;
  onSelectConversation: (threadId: string) => void;
}

function formatRecentTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) {
    return date.toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  return date.toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit"
  });
}

export function ConversationSidebar({
  activeThreadId,
  conversations,
  isLoading,
  onDeleteConversation,
  onNewChat,
  onSelectConversation
}: ConversationSidebarProps) {
  return (
    <div className="conversation-history">
      <Button
        block
        className="new-chat-button"
        icon={<PlusOutlined />}
        onClick={onNewChat}
      >
        新聊天
      </Button>

      <section className="recent-conversation-section" aria-label="最近对话">
        <div className="recent-conversation-heading">
          <span className="sidebar-label">最近</span>
          {isLoading ? <Spin size="small" /> : null}
        </div>

        {conversations.length === 0 ? (
          <Empty
            className="recent-empty"
            description="暂无对话"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <div className="recent-conversation-list">
            {conversations.map((conversation) => {
              const active = conversation.thread_id === activeThreadId;
              return (
                <div
                  className={
                    active
                      ? "recent-conversation-item recent-conversation-item--active"
                      : "recent-conversation-item"
                  }
                  key={conversation.thread_id}
                  title={conversation.title}
                >
                  <button
                    className="recent-conversation-select"
                    onClick={() => onSelectConversation(conversation.thread_id)}
                    type="button"
                  >
                    <MessageOutlined aria-hidden />
                    <span>{conversation.title || "新聊天"}</span>
                  </button>
                  <time dateTime={conversation.last_message_at}>
                    {formatRecentTime(conversation.last_message_at)}
                  </time>
                  <Popconfirm
                    cancelText="取消"
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => onDeleteConversation(conversation.thread_id)}
                    title="删除这条聊天记录？"
                  >
                    <Tooltip title="删除">
                      <Button
                        aria-label={`删除 ${conversation.title || "新聊天"}`}
                        className="recent-conversation-delete"
                        icon={<DeleteOutlined />}
                        shape="circle"
                        type="text"
                      />
                    </Tooltip>
                  </Popconfirm>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}