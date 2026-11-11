"use client";

import { useState } from "react";
import type { Message, SourceInfo, ThinkingSummary, QuestionAnalysis } from "../lib/types";

interface MessageListProps {
  messages: Message[];
  isThinking: boolean;
  onDeleteMessage?: (messageId: string) => void;
}

/**
 * Format inline markdown such as **bold**, *italic*, `code`, and [citations].
 */
function renderInlineMarkdown(text: string) {
  // Split tokens by code, bold, citation, italic
  const parts: React.ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[(?:Page|Source|Doc|Chunk)[^\]]+\])/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code
          key={match.index}
          className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-xs text-purple-300 border border-purple-500/20"
        >
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(
        <strong key={match.index} className="font-semibold text-white">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("*") && token.endsWith("*")) {
      parts.push(
        <em key={match.index} className="italic text-gray-200">
          {token.slice(1, -1)}
        </em>
      );
    } else if (token.startsWith("[") && token.endsWith("]")) {
      parts.push(
        <span
          key={match.index}
          className="inline-flex items-center gap-1 rounded bg-purple-950/60 border border-purple-500/30 px-1.5 py-0.5 font-mono text-[11px] text-purple-300 font-medium"
        >
          📌 {token.slice(1, -1)}
        </span>
      );
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

/**
 * Robust markdown block parser that safely renders headers, code blocks, lists, and paragraphs.
 */
function MarkdownRenderer({ content }: { content: string }) {
  if (!content) return null;

  // Sanitize any leaked specification labels such as (Definition – concise, exam style)**
  const cleanContent = content
    .replace(/(?:\*\*)?\(?\s*Definition\s*[-\u2013\u2014:,]\s*concise,?\s*exam\s*style\s*\)?(?:\*\*)?:?\s*/gi, "")
    .replace(/(?:\*\*)?\(?\s*(?:definition|explanation|short answer|comparison|analytical)\s*[-\u2013\u2014:,]\s*(?:concise|medium|comprehensive|detailed),?\s*exam\s*style\s*\)?(?:\*\*)?:?\s*/gi, "")
    .trim();

  const lines = cleanContent.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeBlockLang = "";
  let codeBlockLines: string[] = [];
  let currentList: { type: "ul" | "ol"; items: string[] } | null = null;

  const flushList = (key: string) => {
    if (!currentList) return;
    const ListTag = currentList.type;
    elements.push(
      <ListTag
        key={key}
        className={`my-2 space-y-1 pl-5 ${
          currentList.type === "ul" ? "list-disc marker:text-purple-400" : "list-decimal marker:text-purple-400"
        } text-sm text-gray-200`}
      >
        {currentList.items.map((item, i) => (
          <li key={i} className="leading-relaxed">
            {renderInlineMarkdown(item)}
          </li>
        ))}
      </ListTag>
    );
    currentList = null;
  };

  lines.forEach((rawLine, index) => {
    const line = rawLine;

    // Handle code fences
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        // End code block
        const codeText = codeBlockLines.join("\n");
        elements.push(
          <div key={`code-${index}`} className="my-3 overflow-hidden rounded-xl border border-white/10 bg-[#0c0d16] shadow-lg">
            {codeBlockLang && (
              <div className="flex items-center justify-between border-b border-white/5 bg-[#141524] px-4 py-1.5 text-[11px] font-mono text-purple-300">
                <span>{codeBlockLang}</span>
              </div>
            )}
            <pre className="overflow-x-auto p-4 font-mono text-xs leading-relaxed text-purple-100">
              <code>{codeText}</code>
            </pre>
          </div>
        );
        inCodeBlock = false;
        codeBlockLines = [];
        codeBlockLang = "";
      } else {
        flushList(`list-before-code-${index}`);
        inCodeBlock = true;
        codeBlockLang = line.trim().slice(3).trim();
        codeBlockLines = [];
      }
      return;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      return;
    }

    // Unordered lists
    const ulMatch = line.match(/^(\s*)[-*+]\s+(.*)$/);
    if (ulMatch) {
      if (!currentList || currentList.type !== "ul") {
        flushList(`flush-before-ul-${index}`);
        currentList = { type: "ul", items: [] };
      }
      currentList.items.push(ulMatch[2]);
      return;
    }

    // Ordered lists
    const olMatch = line.match(/^(\s*)\d+\.\s+(.*)$/);
    if (olMatch) {
      if (!currentList || currentList.type !== "ol") {
        flushList(`flush-before-ol-${index}`);
        currentList = { type: "ol", items: [] };
      }
      currentList.items.push(olMatch[2]);
      return;
    }

    // Flush any pending list if the line is not a list item
    flushList(`flush-list-${index}`);

    // Blank line
    if (!line.trim()) {
      return;
    }

    // Headers
    if (line.startsWith("### ")) {
      elements.push(
        <h3 key={`h3-${index}`} className="mt-4 mb-2 text-base font-bold text-purple-200">
          {renderInlineMarkdown(line.slice(4))}
        </h3>
      );
      return;
    }
    if (line.startsWith("## ")) {
      elements.push(
        <h2 key={`h2-${index}`} className="mt-5 mb-2.5 text-lg font-bold text-white border-b border-white/10 pb-1">
          {renderInlineMarkdown(line.slice(3))}
        </h2>
      );
      return;
    }
    if (line.startsWith("# ")) {
      elements.push(
        <h1 key={`h1-${index}`} className="mt-6 mb-3 text-xl font-extrabold text-white">
          {renderInlineMarkdown(line.slice(2))}
        </h1>
      );
      return;
    }

    // Blockquotes
    if (line.startsWith("> ")) {
      elements.push(
        <blockquote
          key={`quote-${index}`}
          className="my-2.5 border-l-2 border-purple-500/60 bg-purple-950/20 px-3.5 py-2 text-sm italic text-purple-200 rounded-r-lg"
        >
          {renderInlineMarkdown(line.slice(2))}
        </blockquote>
      );
      return;
    }

    // Standard paragraph
    elements.push(
      <p key={`p-${index}`} className="my-2 text-sm leading-relaxed text-gray-200">
        {renderInlineMarkdown(line)}
      </p>
    );
  });

  // Final flush if message ended inside list or code block
  flushList("final-list-flush");
  if (inCodeBlock && codeBlockLines.length > 0) {
    elements.push(
      <pre key="final-code" className="my-3 overflow-x-auto rounded-xl border border-white/10 bg-[#0c0d16] p-4 font-mono text-xs text-purple-100">
        <code>{codeBlockLines.join("\n")}</code>
      </pre>
    );
  }

  return <div className="space-y-1">{elements}</div>;
}

/**
 * AI Thought Process & Evidence Analysis Block
 */
function AIThinkingPanel({
  thinking,
  thinkingSummary,
  questionAnalysis,
  coverage,
  additionalKnowledgeUsed,
}: {
  thinking?: string;
  thinkingSummary?: ThinkingSummary;
  questionAnalysis?: QuestionAnalysis;
  coverage?: string;
  additionalKnowledgeUsed?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);

  const hasContent = Boolean(
    thinking ||
    thinkingSummary?.question_understanding ||
    thinkingSummary?.evidence_analysis ||
    thinkingSummary?.reasoning_summary ||
    questionAnalysis
  );

  if (!hasContent) return null;

  return (
    <div className="mb-3.5 overflow-hidden rounded-xl border border-purple-500/25 bg-[#111224]/90 shadow-md">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-3.5 py-2.5 text-left text-xs font-medium text-purple-300 transition hover:bg-purple-900/20"
      >
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-purple-500/20 text-purple-300 text-xs">
            🧠
          </span>
          <span className="font-semibold text-purple-200">AI Thought Process & Evidence Analysis</span>
          {coverage && (
            <span className="hidden sm:inline-flex ml-1 rounded-full bg-purple-950/80 px-2 py-0.5 text-[10px] text-purple-300 border border-purple-500/30">
              Coverage: {coverage}
            </span>
          )}
        </div>
        <span className="text-[11px] text-purple-400">
          {isOpen ? "Hide process ▲" : "View thinking ▼"}
        </span>
      </button>

      {isOpen && (
        <div className="border-t border-purple-500/15 p-3.5 space-y-3 bg-[#0d0e1c] text-xs leading-relaxed text-gray-300">
          {questionAnalysis && (
            <div className="rounded-lg bg-black/30 p-2.5 border border-white/5">
              <div className="font-semibold text-purple-300 mb-1 flex items-center gap-1.5">
                <span>🎯</span> Question Understanding & Intent
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[11px] text-gray-300">
                {questionAnalysis.topic && (
                  <div><span className="text-gray-400">Topic:</span> {questionAnalysis.topic}</div>
                )}
                {questionAnalysis.intent && (
                  <div><span className="text-gray-400">Intent:</span> {questionAnalysis.intent}</div>
                )}
                {questionAnalysis.question_type && (
                  <div><span className="text-gray-400">Type:</span> {questionAnalysis.question_type}</div>
                )}
              </div>
            </div>
          )}

          {thinkingSummary?.evidence_analysis && (
            <div className="rounded-lg bg-black/30 p-2.5 border border-white/5">
              <div className="font-semibold text-indigo-300 mb-1 flex items-center gap-1.5">
                <span>🔍</span> Knowledge Base & Evidence Analysis
              </div>
              <p className="text-gray-300">{thinkingSummary.evidence_analysis}</p>
            </div>
          )}

          {thinkingSummary?.reasoning_summary && (
            <div className="rounded-lg bg-black/30 p-2.5 border border-white/5">
              <div className="font-semibold text-purple-300 mb-1 flex items-center gap-1.5">
                <span>💡</span> Reasoning & Knowledge Synthesis
              </div>
              <p className="text-gray-300">{thinkingSummary.reasoning_summary}</p>
            </div>
          )}

          {thinking && (
            <div className="rounded-lg bg-black/40 p-2.5 border border-white/5 font-mono text-[11px] text-gray-400 whitespace-pre-wrap max-h-48 overflow-y-auto">
              <div className="font-semibold text-purple-300 font-sans mb-1 flex items-center gap-1">
                <span>⚙️</span> Chain of Thought Log
              </div>
              {thinking}
            </div>
          )}

          {additionalKnowledgeUsed && (
            <div className="text-[11px] text-amber-300/90 flex items-center gap-1.5 pt-1">
              <span>✨</span>
              <span>Reasoning supplemented with foundational AI knowledge where the PDF had gaps.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Sources and Evidence List - Clean, simple display showing only unique lesson name
 */
function SourcesFootnote({ sources }: { sources?: SourceInfo[] }) {
  if (!sources || sources.length === 0) return null;

  // Extract unique, clean lesson names (deduplicated)
  const lessonNames = Array.from(
    new Set(
      sources
        .map((src) => {
          const raw = src.lesson_name || src.pdf_name || src.document_name || "";
          return raw.replace(/\.pdf$/i, "").trim();
        })
        .filter(Boolean)
    )
  );

  if (lessonNames.length === 0) return null;

  return (
    <div className="mt-3.5 pt-3 border-t border-white/10 flex items-center gap-2 text-xs text-gray-400">
      <span className="text-purple-400 font-medium">Evidence:</span>
      <span className="text-gray-200 font-medium">{lessonNames.join(", ")}</span>
    </div>
  );
}

function MessageBubble({ message, onDeleteMessage }: { message: Message; onDeleteMessage?: (messageId: string) => void }) {
  const isUser = message.role === "user";

  return (
    <div className={`group/msg flex ${isUser ? "justify-end" : "justify-start"} w-full animate-in fade-in slide-in-from-bottom-2 duration-200`}>
      {/* Delete button — left side for user messages */}
      {isUser && onDeleteMessage && (
        <button
          type="button"
          onClick={() => onDeleteMessage(message.id)}
          className="mr-2 mt-3 shrink-0 rounded-md p-1.5 text-gray-600 opacity-0 transition hover:bg-red-500/15 hover:text-red-400 group-hover/msg:opacity-100"
          title="Delete this message"
          aria-label="Delete message"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      )}
      <div
        className={`max-w-[90%] sm:max-w-[85%] rounded-2xl px-5 py-4 ${
          isUser
            ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-br-sm shadow-lg shadow-purple-950/20"
            : "bg-[#131422]/95 text-gray-100 border border-white/10 rounded-bl-sm shadow-xl backdrop-blur-md"
        }`}
      >
        {isUser ? (
          <>
            <div className="whitespace-pre-wrap font-sans text-sm sm:text-base leading-relaxed">{message.content}</div>
            {message.images && message.images.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {message.images.map((image, index) => (
                  <img
                    key={`${message.id}-image-${index}`}
                    src={image}
                    alt={`Attached image ${index + 1}`}
                    className="max-h-48 max-w-full rounded-lg border border-white/15 object-contain"
                  />
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="w-full">
            {/* AI Thought Process Panel */}
            <AIThinkingPanel
              thinking={message.thinking}
              thinkingSummary={message.thinking_summary}
              questionAnalysis={message.question_analysis}
              coverage={message.knowledge_coverage}
              additionalKnowledgeUsed={message.additional_knowledge_used}
            />

            {/* Answer Content */}
            <MarkdownRenderer content={message.content} />

            {/* Evidence Citations */}
            <SourcesFootnote sources={message.sources} />
          </div>
        )}
      </div>
      {/* Delete button — right side for assistant messages */}
      {!isUser && onDeleteMessage && (
        <button
          type="button"
          onClick={() => onDeleteMessage(message.id)}
          className="ml-2 mt-3 shrink-0 rounded-md p-1.5 text-gray-600 opacity-0 transition hover:bg-red-500/15 hover:text-red-400 group-hover/msg:opacity-100"
          title="Delete this message"
          aria-label="Delete message"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      )}
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex justify-start w-full animate-in fade-in duration-200">
      <div className="bg-[#131422]/90 border border-purple-500/20 rounded-2xl rounded-bl-sm px-5 py-3.5 shadow-xl backdrop-blur-md">
        <div className="flex items-center gap-3 text-xs text-purple-300">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
          <span className="font-medium text-gray-200">Analyzing knowledge base and thinking...</span>
        </div>
      </div>
    </div>
  );
}

export function MessageList({ messages, isThinking, onDeleteMessage }: MessageListProps) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} onDeleteMessage={onDeleteMessage} />
      ))}

      {isThinking && <ThinkingIndicator />}
    </div>
  );
}
