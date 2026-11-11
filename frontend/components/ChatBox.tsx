"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import Link from "next/link";
import { api, type AskResponse, type AskRequest, type SessionResponse, type Lesson } from "../lib/api";
import { MessageList } from "./MessageList";
import { PromoVerificationModal } from "./PromoVerificationModal";
import type { ChatConversation, Message } from "../lib/types";

const CHAT_HISTORY_KEY = "ruixen_chat_history_v1";
const MAX_IMAGE_ATTACHMENTS = 3;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

interface PendingImage {
  id: string;
  name: string;
  dataUrl: string;
  previewUrl: string;
}

interface ChatBoxProps {
  session: SessionResponse | null;
  lessons: Lesson[];
  selectedLessonId: string | null;
  onSelectLesson: (lessonId: string | null) => void;
}

function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read the selected image."));
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("The selected image could not be converted."));
      }
    };
    reader.readAsDataURL(file);
  });
}

async function createImagePreview(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 512 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new Error("Could not prepare an image preview.");
  }
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();

  const preview = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Could not prepare an image preview."))),
      "image/jpeg",
      0.7
    );
  });
  return readAsDataUrl(preview);
}

export function ChatBox({
  session,
  lessons,
  selectedLessonId,
  onSelectLesson,
}: ChatBoxProps) {
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPromoVerified, setIsPromoVerified] = useState(false);
  const [verifiedPromoCode, setVerifiedPromoCode] = useState<string | null>(null);
  const [verifiedPromoLabel, setVerifiedPromoLabel] = useState<string | null>(null);
  const [isPromoModalOpen, setIsPromoModalOpen] = useState(true);
  const [tamperAlert, setTamperAlert] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-adjust textarea height as user types long text
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "auto";
    const minHeight = 38;
    const maxHeight = 160;
    const targetHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight);

    textarea.style.height = `${targetHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [input]);

  const safeLessons = useMemo(() => (Array.isArray(lessons) ? lessons : []), [lessons]);
  const safeConversations = useMemo(
    () => (Array.isArray(conversations) ? conversations : []),
    [conversations]
  );

  const activeConversation = useMemo(
    () => safeConversations.find((conversation) => conversation.id === activeConversationId),
    [activeConversationId, safeConversations]
  );
  const messages = activeConversation?.messages ?? [];
  const activeLesson = useMemo(
    () => safeLessons.find((l) => l.id === selectedLessonId),
    [safeLessons, selectedLessonId]
  );

  useEffect(() => {
    try {
      const saved = localStorage.getItem(CHAT_HISTORY_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as ChatConversation[];
        const valid = parsed
          .filter(
            (conversation) =>
              conversation &&
              typeof conversation.id === "string" &&
              typeof conversation.title === "string" &&
              Array.isArray(conversation.messages)
          )
          .map((conversation) => ({
            ...conversation,
            messages: conversation.messages.map((message) => ({
              ...message,
              timestamp: new Date(message.timestamp),
            })),
          }))
          .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
        setConversations(valid);
        setActiveConversationId(valid[0]?.id ?? null);
        onSelectLesson(valid[0]?.lessonId ?? null);
      }
    } catch (storageError) {
      setHistoryError(
        storageError instanceof Error
          ? `Could not load saved chats: ${storageError.message}`
          : "Could not load saved chats from this browser."
      );
    } finally {
      setHistoryLoaded(true);
    }
  }, [onSelectLesson]);

  useEffect(() => {
    if (!historyLoaded) return;
    try {
      localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(conversations));
      setHistoryError(null);
    } catch (storageError) {
      setHistoryError(
        storageError instanceof Error
          ? `Chat history could not be saved: ${storageError.message}`
          : "Chat history could not be saved in this browser."
      );
    }
  }, [conversations, historyLoaded]);

  // Check saved promo verification token on initial page load
  useEffect(() => {
    const checkSavedPromo = async () => {
      const savedToken = localStorage.getItem("rag_promo_token");
      const savedCode = localStorage.getItem("rag_promo_code");
      const savedLabel = localStorage.getItem("rag_promo_label");

      if (savedToken) {
        try {
          const res = await api.checkPromoToken(savedToken);
          if (res.valid) {
            setIsPromoVerified(true);
            setVerifiedPromoCode(res.code || savedCode || "VERIFIED");
            setVerifiedPromoLabel(res.label || savedLabel || null);
            setIsPromoModalOpen(false);
            return;
          }
        } catch {
          // Token invalid or network issue
        }
      }

      // If no valid promo token found, lock chat and force modal open
      localStorage.removeItem("rag_promo_token");
      localStorage.removeItem("rag_promo_code");
      localStorage.removeItem("rag_promo_label");
      setIsPromoVerified(false);
      setVerifiedPromoCode(null);
      setVerifiedPromoLabel(null);
      setIsPromoModalOpen(true);
    };

    void checkSavedPromo();
  }, []);

  // Anti-tamper security guard:
  // Detects if user modifies HTML in DevTools to remove modal or remove 'disabled' attribute
  useEffect(() => {
    if (isPromoVerified) return;

    const interval = setInterval(() => {
      if (!isPromoVerified) {
        const overlay = document.getElementById("promo-verification-overlay");
        // If someone deleted the popup overlay from DOM while unverified:
        if (!overlay) {
          setIsPromoModalOpen(true);
          setInput("");
          setTamperAlert("Security Notice: Chat typing is disabled until a valid promo code is verified.");
        }
        // If someone removed the disabled attribute from textarea:
        if (textareaRef.current && !textareaRef.current.disabled) {
          textareaRef.current.disabled = true;
          textareaRef.current.value = "";
          setInput("");
        }
      }
    }, 700);

    return () => clearInterval(interval);
  }, [isPromoVerified]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isThinking, scrollToBottom]);

  const appendToConversation = useCallback(
    (conversationId: string, additions: Message[], firstQuestion: string) => {
      setConversations((current) => {
        const existing = current.find((conversation) => conversation.id === conversationId);
        const updated: ChatConversation = {
          id: conversationId,
          title: existing?.title && existing.title !== "New chat"
            ? existing.title
            : firstQuestion.slice(0, 48) || "Image question",
          messages: [...(existing?.messages ?? []), ...additions],
          updatedAt: new Date().toISOString(),
          lessonId: selectedLessonId,
        };
        return [updated, ...current.filter((conversation) => conversation.id !== conversationId)];
      });
    },
    [selectedLessonId]
  );

  const handleImageSelect = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;

    if (!isPromoVerified) {
      setIsPromoModalOpen(true);
      return;
    }

    if (pendingImages.length + files.length > MAX_IMAGE_ATTACHMENTS) {
      setError(`Attach up to ${MAX_IMAGE_ATTACHMENTS} images per message.`);
      return;
    }

    const invalidFile = files.find(
      (file) =>
        !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
        file.size > MAX_IMAGE_BYTES
    );
    if (invalidFile) {
      setError(
        invalidFile.size > MAX_IMAGE_BYTES
          ? `${invalidFile.name} exceeds the 5MB image limit.`
          : `${invalidFile.name} is not a supported PNG, JPEG, or WebP image.`
      );
      return;
    }

    try {
      const selected = await Promise.all(
        files.map(async (file): Promise<PendingImage> => {
          const dataUrl = await readAsDataUrl(file);
          const previewUrl = await createImagePreview(file);
          return { id: crypto.randomUUID(), name: file.name, dataUrl, previewUrl };
        })
      );
      setPendingImages((current) => [...current, ...selected]);
      setError(null);
    } catch (imageError) {
      setError(
        imageError instanceof Error ? imageError.message : "Could not load the selected image."
      );
    }
  }, [pendingImages.length]);

  const handleSubmit = useCallback(async (event?: React.FormEvent) => {
    if (event) event.preventDefault();

    if (!isPromoVerified) {
      setIsPromoModalOpen(true);
      setError("Please enter and verify your promo code to unlock the chat.");
      return;
    }

    if ((!input.trim() && pendingImages.length === 0) || isThinking) return;

    const question = input.trim() || "Describe the attached image.";
    const conversationId = activeConversationId ?? crypto.randomUUID();
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
      images: pendingImages.map((image) => image.previewUrl),
      timestamp: new Date(),
    };

    setActiveConversationId(conversationId);
    appendToConversation(conversationId, [userMessage], question);
    setInput("");
    const images = pendingImages.map((image) => image.dataUrl);
    setPendingImages([]);
    setIsThinking(true);
    setError(null);

    try {
      const request: AskRequest = {
        question,
        lesson_id: selectedLessonId || undefined,
        images: images.length ? images : undefined,
      };

      const response: AskResponse = await api.askQuestionStream(
        session?.access_token || null,
        request
      );

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: response.answer,
        question_analysis: response.question_analysis,
        thinking_summary: response.thinking_summary,
        sources: response.sources,
        answer_status: response.answer_status,
        abstained: response.abstained,
        thinking: response.thinking,
        question_type: response.question_type,
        knowledge_coverage: response.knowledge_coverage,
        additional_knowledge_used: response.additional_knowledge_used,
        timestamp: new Date(),
      };

      appendToConversation(conversationId, [assistantMessage], question);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to get answer";
      setError(message);

      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Error: ${message}`,
        timestamp: new Date(),
      };
      appendToConversation(conversationId, [errorMessage], question);
    } finally {
      setIsThinking(false);
    }
  }, [
    input,
    isThinking,
    isPromoVerified,
    session,
    selectedLessonId,
    pendingImages,
    activeConversationId,
    appendToConversation,
  ]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!isPromoVerified) {
      event.preventDefault();
      setIsPromoModalOpen(true);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const handlePromoVerified = useCallback((code: string, _token: string, label?: string) => {
    setIsPromoVerified(true);
    setVerifiedPromoCode(code);
    setVerifiedPromoLabel(label || null);
    setIsPromoModalOpen(false);
    setTamperAlert(null);
    setError(null);
  }, []);

  const handleResetPromo = useCallback(() => {
    localStorage.removeItem("rag_promo_token");
    localStorage.removeItem("rag_promo_code");
    localStorage.removeItem("rag_promo_label");
    setIsPromoVerified(false);
    setVerifiedPromoCode(null);
    setVerifiedPromoLabel(null);
    setIsPromoModalOpen(true);
  }, []);

  const hasMessages = messages.length > 0;

  const startNewChat = () => {
    setActiveConversationId(null);
    setPendingImages([]);
    setInput("");
    setError(null);
    setIsHistoryOpen(false);
  };

  const openConversation = (conversation: ChatConversation) => {
    setActiveConversationId(conversation.id);
    onSelectLesson(conversation.lessonId ?? null);
    setPendingImages([]);
    setError(null);
    setIsHistoryOpen(false);
  };

  const deleteConversation = useCallback((conversationId: string) => {
    setConversations((current) => current.filter((c) => c.id !== conversationId));
    if (activeConversationId === conversationId) {
      setActiveConversationId(null);
      setPendingImages([]);
      setInput("");
      setError(null);
    }
  }, [activeConversationId]);

  const deleteMessage = useCallback((messageId: string) => {
    if (!activeConversationId) return;
    setConversations((current) =>
      current.map((conv) => {
        if (conv.id !== activeConversationId) return conv;
        const filtered = conv.messages.filter((m) => m.id !== messageId);
        return { ...conv, messages: filtered, updatedAt: new Date().toISOString() };
      }).filter((conv) => conv.messages.length > 0)
    );
  }, [activeConversationId]);

  const clearAllChats = useCallback(() => {
    setConversations([]);
    setActiveConversationId(null);
    setPendingImages([]);
    setInput("");
    setError(null);
  }, []);

  return (
    <div className="relative flex h-full w-full overflow-hidden">
      <div className="pointer-events-none absolute left-1/2 top-[42%] z-0 h-[280px] w-[min(90vw,950px)] -translate-x-1/2 -translate-y-1/2 rounded-[100%] bg-gradient-to-t from-transparent via-[#4f46e5]/25 to-[#9333ea]/35 blur-3xl sm:h-[450px]" />

      {isHistoryOpen && (
        <button
          type="button"
          className="absolute inset-0 z-30 bg-black/60 md:hidden"
          onClick={() => setIsHistoryOpen(false)}
          aria-label="Close chat history"
        />
      )}
      <aside
        className={`absolute inset-y-0 left-0 z-40 flex w-[min(82vw,300px)] flex-col border-r border-white/10 bg-[#0b0c13]/95 p-4 backdrop-blur-xl transition-transform md:relative md:z-10 md:w-64 md:translate-x-0 ${
          isHistoryOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsHistoryOpen(false)}
              className="rounded p-1 text-gray-400 hover:text-white md:hidden"
              aria-label="Close sidebar"
            >
              ✕
            </button>
            <span className="font-semibold text-white">Chat history</span>
          </div>
          <button
            type="button"
            onClick={startNewChat}
            className="rounded-lg border border-purple-400/30 bg-purple-600/15 px-3 py-2 text-xs font-medium text-purple-200 hover:bg-purple-600/25"
          >
            + New chat
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
          {conversations.length === 0 ? (
            <p className="px-2 py-3 text-xs text-gray-500">Your saved chats will appear here.</p>
          ) : (
            conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={`group flex items-center rounded-lg transition ${
                  conversation.id === activeConversationId
                    ? "bg-white/10 text-white"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                <button
                  type="button"
                  onClick={() => openConversation(conversation)}
                  className="min-w-0 flex-1 truncate px-3 py-2.5 text-left text-xs"
                  title={conversation.title}
                >
                  {conversation.title}
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteConversation(conversation.id);
                  }}
                  className="mr-1.5 shrink-0 rounded p-1 text-gray-600 opacity-0 transition hover:bg-red-500/20 hover:text-red-400 group-hover:opacity-100"
                  title="Delete chat"
                  aria-label={`Delete chat: ${conversation.title}`}
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-white/10 pt-3 text-[10px] text-gray-600">
          <div className="flex items-center gap-3">
            <span>Chats saved in browser</span>
            {conversations.length > 0 && (
              <button
                type="button"
                onClick={clearAllChats}
                className="text-gray-600 transition hover:text-red-400"
                title="Clear all chats"
              >
                Clear all
              </button>
            )}
          </div>
          <Link
            href="/admin"
            className="flex items-center gap-1 text-gray-500 hover:text-purple-300 transition"
          >
            <span>⚙️</span>
            <span>Admin</span>
          </Link>
        </div>
      </aside>

      <section className="relative z-10 flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="absolute right-4 top-3.5 z-20 hidden items-center gap-2 md:flex">
          {/* Promo Code Status Pill */}
          {isPromoVerified ? (
            <div className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-[#101915]/90 px-2.5 py-1 text-xs text-emerald-300 backdrop-blur-sm shadow-sm">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="font-mono text-[11px] font-semibold">{verifiedPromoCode}</span>
              <button
                type="button"
                onClick={handleResetPromo}
                className="ml-1 text-[10px] text-gray-400 hover:text-white underline"
                title="Change Promo Code"
              >
                Change
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setIsPromoModalOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-950/40 px-2.5 py-1 text-xs font-medium text-amber-300 transition hover:border-amber-400 backdrop-blur-sm shadow-[0_0_15px_rgba(245,158,11,0.2)]"
            >
              <span>🔒</span>
              <span>Enter Promo Code</span>
            </button>
          )}

          <Link
            href="/admin"
            className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-[#11121b]/40 px-2.5 py-1 text-xs text-gray-500 transition hover:border-purple-500/30 hover:bg-[#11121b]/80 hover:text-purple-300 backdrop-blur-sm"
            title="Admin Dashboard & Knowledge Base"
          >
            <span className="text-[11px]">⚙️</span>
            <span>Admin</span>
          </Link>
        </div>
        <div className="absolute left-3 right-3 top-3 z-20 flex items-center justify-between md:hidden">
          <button
            type="button"
            onClick={() => setIsHistoryOpen(true)}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-[#11121b]/90 px-2.5 py-1.5 text-xs text-gray-200 backdrop-blur"
            aria-label="Open sidebar"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
            <span>History</span>
          </button>
          <div className="flex items-center gap-2">
            {!isPromoVerified ? (
              <button
                type="button"
                onClick={() => setIsPromoModalOpen(true)}
                className="rounded-lg border border-amber-500/40 bg-amber-950/60 px-2.5 py-1.5 text-xs font-medium text-amber-300"
              >
                🔒 Unlock
              </button>
            ) : (
              <span className="rounded-lg border border-emerald-500/30 bg-emerald-950/40 px-2 py-1 font-mono text-[11px] text-emerald-300">
                {verifiedPromoCode}
              </span>
            )}
          </div>
        </div>

        {hasMessages && (
          <div className="z-10 flex items-center justify-between border-b border-white/10 bg-[#0C0D14]/80 px-4 py-3 pt-14 backdrop-blur-md sm:px-6 md:pt-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className="shrink-0 bg-gradient-to-r from-purple-400 to-indigo-300 bg-clip-text text-base font-bold text-transparent">
                Ruixen AI
              </span>
              {activeLesson && (
                <span className="truncate rounded-full border border-purple-500/30 bg-purple-500/20 px-2.5 py-0.5 text-xs font-medium text-purple-300">
                  {activeLesson.title}
                </span>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {activeConversationId && (
                <button
                  type="button"
                  onClick={() => deleteConversation(activeConversationId)}
                  className="rounded-md px-2 py-1 text-xs text-gray-500 transition hover:bg-red-500/10 hover:text-red-400"
                  title="Delete this chat"
                >
                  <svg className="inline h-3.5 w-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Delete
                </button>
              )}
              <button
                type="button"
                onClick={startNewChat}
                className="rounded-md px-2.5 py-1 text-xs text-gray-400 transition hover:bg-white/5 hover:text-gray-200"
              >
                New Chat
              </button>
            </div>
          </div>
        )}

        {hasMessages ? (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-4xl">
              <MessageList messages={messages} isThinking={isThinking} onDeleteMessage={deleteMessage} />
              <div ref={messagesEndRef} />
            </div>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 select-none flex-col items-center justify-center px-4 pb-12 text-center">
            <h1 className="mb-3 text-4xl font-bold tracking-tight text-white sm:text-5xl md:text-6xl">
              Ruixen AI
            </h1>
            <p className="mx-auto max-w-md text-sm font-normal text-gray-400 sm:text-base">
              Build something amazing — just start typing below.
            </p>
            {activeLesson && (
              <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-purple-500/30 bg-purple-900/40 px-3.5 py-1.5 text-xs font-medium text-purple-200">
                <span>Selected Lesson: <strong>{activeLesson.title}</strong></span>
                <button
                  type="button"
                  onClick={() => onSelectLesson(null)}
                  className="ml-1 transition hover:text-white"
                  title="Clear selection"
                >
                  ✕
                </button>
              </div>
            )}
          </div>
        )}

        <div className="z-20 mx-auto w-full max-w-3xl px-4 pb-4 pt-2 sm:pb-6">
          {/* Security alerts and error banners */}
          {(tamperAlert || error || historyError) && (
            <div className="mb-3 space-y-2">
              {tamperAlert && (
                <div className="flex items-center justify-between rounded-xl border border-amber-500/40 bg-amber-950/60 p-3 text-xs text-amber-200 shadow-md">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">🛡️</span>
                    <span>{tamperAlert}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setTamperAlert(null);
                      setIsPromoModalOpen(true);
                    }}
                    className="ml-3 rounded bg-amber-600/30 px-2 py-1 text-[11px] font-medium text-amber-100 hover:bg-amber-600/50"
                  >
                    Enter Code
                  </button>
                </div>
              )}
              {[error, historyError].filter(Boolean).map((message) => (
                <div
                  key={message}
                  className="flex items-center justify-between rounded-xl border border-red-500/30 bg-red-950/40 p-3 text-xs text-red-300"
                >
                  <span>{message}</span>
                  <button
                    type="button"
                    onClick={() => {
                      setError(null);
                      setHistoryError(null);
                    }}
                    className="ml-3 text-gray-400 hover:text-white"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}

          {pendingImages.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {pendingImages.map((image) => (
                <div
                  key={image.id}
                  className="relative h-16 w-16 overflow-hidden rounded-lg border border-white/15"
                  title={image.name}
                >
                  <img src={image.previewUrl} alt={image.name} className="h-full w-full object-cover" />
                  <button
                    type="button"
                    onClick={() => setPendingImages((current) => current.filter((item) => item.id !== image.id))}
                    className="absolute right-1 top-1 rounded-full bg-black/75 px-1 text-xs text-white"
                    aria-label={`Remove ${image.name}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="relative rounded-2xl border border-white/15 bg-[#12131F]/90 p-3 shadow-2xl shadow-purple-950/30 backdrop-blur-xl transition focus-within:border-purple-500/50 sm:p-4">
            {/* Protective security overlay barrier if chat is not verified */}
            {!isPromoVerified && (
              <div
                onClick={() => setIsPromoModalOpen(true)}
                className="absolute inset-0 z-30 flex cursor-pointer items-center justify-center rounded-2xl bg-[#090a12]/80 backdrop-blur-[2px] transition hover:bg-[#090a12]/70"
                title="Click to enter Promo Code and unlock typing"
              >
                <div className="flex items-center gap-2 rounded-full border border-purple-500/40 bg-[#161726]/95 px-4 py-2 text-xs font-medium text-purple-200 shadow-xl shadow-purple-950/50">
                  <span className="text-sm">🔒</span>
                  <span>Promo code required. Click to unlock typing</span>
                </div>
              </div>
            )}

            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                if (!isPromoVerified) {
                  setIsPromoModalOpen(true);
                  return;
                }
                setInput(e.target.value);
              }}
              onKeyDown={handleKeyDown}
              placeholder={
                !isPromoVerified
                  ? "🔒 Chat locked. Enter a promo code to unlock typing..."
                  : "Type your request..."
              }
              rows={1}
              disabled={isThinking || !isPromoVerified}
              readOnly={!isPromoVerified}
              className="min-h-[38px] max-h-40 w-full resize-none bg-transparent pr-12 font-sans text-sm text-white outline-none placeholder-gray-500 sm:text-base disabled:opacity-40 leading-relaxed py-1"
              aria-label="Ask a question"
            />

            <div className="mt-1 flex items-center justify-between border-t border-white/5 pt-2">
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  onChange={handleImageSelect}
                  className="hidden"
                  aria-label="Attach images"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isThinking || !isPromoVerified || pendingImages.length >= MAX_IMAGE_ATTACHMENTS}
                  className="rounded-md p-1 text-gray-400 transition hover:bg-white/5 hover:text-white disabled:opacity-30"
                  title="Attach images for visual analysis"
                  aria-label="Attach images"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                </button>
                {pendingImages.length > 0 && (
                  <span className="text-[11px] text-gray-500">{pendingImages.length} image(s)</span>
                )}
              </div>

              <button
                type="button"
                onClick={() => handleSubmit()}
                disabled={(!input.trim() && pendingImages.length === 0) || isThinking || !isPromoVerified}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-white shadow-md transition hover:bg-purple-600 disabled:opacity-30 disabled:hover:bg-white/10"
                aria-label="Send"
              >
                {isThinking ? (
                  <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <span className="text-sm font-bold">↑</span>
                )}
              </button>
            </div>
          </div>

          {safeLessons.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2 px-2">
              {safeLessons.map((lesson) => {
                const isSelected = selectedLessonId === lesson.id;
                return (
                  <button
                    type="button"
                    key={lesson.id}
                    onClick={() => onSelectLesson(isSelected ? null : lesson.id)}
                    className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                      isSelected
                        ? "border-purple-400 bg-purple-600/30 text-purple-200 shadow-sm shadow-purple-500/20"
                        : "border-white/10 bg-[#141522]/80 text-gray-400 hover:border-white/25 hover:text-white"
                    }`}
                  >
                    <span>📚</span>
                    <span>{lesson.title}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* Promo Code Verification Popup Modal */}
      <PromoVerificationModal
        isOpen={!isPromoVerified || isPromoModalOpen}
        onVerified={handlePromoVerified}
      />
    </div>
  );
}
