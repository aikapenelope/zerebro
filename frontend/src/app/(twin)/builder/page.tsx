"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { AgentConfigPreview } from "@/components/agent-config-preview";
import {
  builderChat,
  cancelSession,
  confirmSession,
  listBuilderSessions,
} from "@/lib/api";
import type {
  AgentConfig,
  BuilderSession,
  ConversationMessage,
  SessionStatus,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// ---------------------------------------------------------------------------
// Builder Page
// ---------------------------------------------------------------------------

export default function BuilderPage() {
  const router = useRouter();

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("active");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [proposedConfig, setProposedConfig] = useState<AgentConfig | null>(null);

  // Input state
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Session list (sidebar)
  const [sessions, setSessions] = useState<BuilderSession[]>([]);

  // Scroll to bottom on new messages
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load sessions on mount
  useEffect(() => {
    listBuilderSessions()
      .then(setSessions)
      .catch(() => {
        /* backend may not be running */
      });
  }, []);

  // Load an existing session into the chat
  const loadSession = useCallback((session: BuilderSession) => {
    setSessionId(session.id);
    setSessionStatus(session.status);
    setMessages(
      session.messages.map((m: ConversationMessage) => ({
        role: m.role,
        content: m.content,
      })),
    );
    setProposedConfig(session.proposed_config);
  }, []);

  // Start a new session
  const newSession = useCallback(() => {
    setSessionId(null);
    setSessionStatus("active");
    setMessages([]);
    setProposedConfig(null);
    setInput("");
  }, []);

  // Send a message to the builder
  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    setSending(true);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");

    try {
      const res = await builderChat({
        session_id: sessionId,
        message: text,
      });

      setSessionId(res.session_id);
      setSessionStatus(res.status);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.response },
      ]);

      if (res.proposed_config) {
        setProposedConfig(res.proposed_config);
      }

      // Refresh session list
      listBuilderSessions()
        .then(setSessions)
        .catch(() => {});
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Failed to reach backend"}`,
        },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, sending, sessionId]);

  // Confirm the proposed agent
  const handleConfirm = useCallback(async () => {
    if (!sessionId) return;
    setConfirming(true);
    try {
      const agent = await confirmSession(sessionId);
      setSessionStatus("confirmed");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Agent "${agent.name}" has been created and registered.`,
        },
      ]);
      // Refresh sessions
      listBuilderSessions()
        .then(setSessions)
        .catch(() => {});
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Failed to confirm: ${err instanceof Error ? err.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setConfirming(false);
    }
  }, [sessionId]);

  // Cancel the session
  const handleCancel = useCallback(async () => {
    if (!sessionId) return;
    try {
      await cancelSession(sessionId);
      setSessionStatus("cancelled");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Session cancelled." },
      ]);
      listBuilderSessions()
        .then(setSessions)
        .catch(() => {});
    } catch {
      /* ignore */
    }
  }, [sessionId]);

  const canChat = sessionStatus === "active" || sessionStatus === "proposed";

  return (
    <div className="flex h-full">
      {/* Session sidebar */}
      <aside className="hidden w-64 flex-col border-r md:flex">
        <div className="flex items-center justify-between p-3">
          <span className="text-sm font-medium">Sessions</span>
          <Button variant="ghost" size="sm" onClick={newSession}>
            New
          </Button>
        </div>
        <Separator />
        <ScrollArea className="flex-1">
          <div className="space-y-1 p-2">
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => loadSession(s)}
                className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
                  s.id === sessionId ? "bg-accent" : ""
                }`}
              >
                <p className="truncate font-medium">
                  {s.messages[0]?.content.slice(0, 40) || "New session"}
                </p>
                <p className="text-xs text-muted-foreground">{s.status}</p>
              </button>
            ))}
            {sessions.length === 0 && (
              <p className="px-3 py-2 text-xs text-muted-foreground">
                No sessions yet. Start chatting!
              </p>
            )}
          </div>
        </ScrollArea>
      </aside>

      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {/* Messages */}
        <ScrollArea className="flex-1 p-4">
          <div className="mx-auto max-w-2xl space-y-4">
            {messages.length === 0 && (
              <div className="flex h-64 items-center justify-center text-center">
                <div>
                  <p className="text-lg font-medium">
                    What agent do you want to build?
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Describe what you need and I&apos;ll create it for you.
                  </p>
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))}

            {/* Proposed config preview */}
            {proposedConfig && sessionStatus === "proposed" && (
              <div className="space-y-3">
                <AgentConfigPreview config={proposedConfig} />
                <div className="flex gap-2">
                  <Button
                    onClick={handleConfirm}
                    disabled={confirming}
                    className="gap-2"
                  >
                    {confirming ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Check className="h-4 w-4" />
                    )}
                    Confirm Agent
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleCancel}
                    className="gap-2"
                  >
                    <X className="h-4 w-4" />
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {sessionStatus === "confirmed" && (
              <div className="rounded-md border border-green-500/30 bg-green-500/10 p-4 text-sm">
                Agent confirmed and registered.{" "}
                <button
                  onClick={() => router.push("/agents")}
                  className="underline"
                >
                  View agents
                </button>
              </div>
            )}

            <div ref={scrollRef} />
          </div>
        </ScrollArea>

        {/* Input */}
        <div className="border-t p-4">
          <div className="mx-auto flex max-w-2xl gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder={
                canChat
                  ? "Describe what you want..."
                  : "Session ended"
              }
              disabled={!canChat || sending}
              className="min-h-[44px] resize-none"
              rows={1}
            />
            <Button
              onClick={sendMessage}
              disabled={!canChat || sending || !input.trim()}
              size="icon"
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
