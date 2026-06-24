import { useCallback, useState } from "react";
import type { ChatTurn } from "../components/ConversationThread";
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations
} from "../lib/api";
import { createThreadId, getStoredThreadId, storeThreadId } from "../lib/thread";
import type {
  ChatConversationRecord,
  ChatMessageRecord,
  MonitorMessage,
  OutputFile
} from "../types";

function createTurnId(): string {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function pairMessages(messages: ChatMessageRecord[]): ChatTurn[] {
  const turns: ChatTurn[] = [];

  messages.forEach((message) => {
    if (message.role === "user") {
      turns.push({
        id: message.id || createTurnId(),
        content: message.content,
        events: [],
        files: [],
        isRunning: false,
        result: "",
        timestamp: message.created_at
      });
      return;
    }

    if (message.role === "assistant") {
      const latestTurn = turns[turns.length - 1];
      if (latestTurn && !latestTurn.result) {
        latestTurn.result = message.content;
        latestTurn.events = (message.events || []) as MonitorMessage[];
        latestTurn.files = (message.files || []) as OutputFile[];
        return;
      }

      turns.push({
        id: message.id || createTurnId(),
        content: "",
        events: (message.events || []) as MonitorMessage[],
        files: (message.files || []) as OutputFile[],
        isRunning: false,
        result: message.content,
        timestamp: message.created_at
      });
    }
  });

  return turns;
}

export function useConversationHistory() {
  const [activeThreadId, setActiveThreadIdState] = useState(getStoredThreadId);
  const [conversations, setConversations] = useState<ChatConversationRecord[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const setActiveThreadId = useCallback((threadId: string) => {
    storeThreadId(threadId);
    setActiveThreadIdState(threadId);
  }, []);

  const refreshConversations = useCallback(async () => {
    const items = await listConversations();
    setConversations(items);
    return items;
  }, []);

  const startNewConversation = useCallback(async () => {
    const nextThreadId = createThreadId();
    const item = await createConversation(nextThreadId, "新聊天");
    setActiveThreadId(item.thread_id);
    setConversations((previous) => [
      item,
      ...previous.filter((conversation) => conversation.thread_id !== item.thread_id)
    ]);
    return item.thread_id;
  }, [setActiveThreadId]);

  const loadConversationTurns = useCallback(
    async (threadId: string) => {
      setIsLoadingHistory(true);
      try {
        const detail = await getConversation(threadId);
        setActiveThreadId(detail.thread_id);
        return pairMessages(detail.messages);
      } finally {
        setIsLoadingHistory(false);
      }
    },
    [setActiveThreadId]
  );

  const removeConversation = useCallback(async (threadId: string) => {
    await deleteConversation(threadId);
    setConversations((previous) =>
      previous.filter((conversation) => conversation.thread_id !== threadId)
    );
  }, []);

  return {
    activeThreadId,
    conversations,
    isLoadingHistory,
    loadConversationTurns,
    removeConversation,
    refreshConversations,
    setActiveThreadId,
    startNewConversation
  };
}
