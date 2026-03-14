"use client";

import { useCallback, useRef, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { streamAgent } from "@/lib/api";

/**
 * Panel for running an agent with SSE streaming output.
 */
export function AgentRunPanel({ agentId }: { agentId: string }) {
  const [message, setMessage] = useState("");
  const [output, setOutput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleRun = useCallback(async () => {
    const text = message.trim();
    if (!text || running) return;

    setRunning(true);
    setOutput("");
    setError(null);

    try {
      const res = await streamAgent({ agent_id: agentId, message: text });
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data:")) {
            const data = line.slice(5).trim();
            if (!data) continue;

            try {
              // SSE events from sse-starlette come as JSON strings
              const parsed = JSON.parse(data) as string;
              if (typeof parsed === "string") {
                setOutput((prev) => prev + parsed);
              }
            } catch {
              // Raw text token
              setOutput((prev) => prev + data);
            }
          } else if (line.startsWith("event:") && line.includes("error")) {
            setError("Agent execution failed. Check backend logs.");
          }
        }

        scrollRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to run agent",
      );
    } finally {
      setRunning(false);
    }
  }, [agentId, message, running]);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleRun();
            }
          }}
          placeholder="Enter a message to run the agent..."
          disabled={running}
          className="min-h-[44px] resize-none"
          rows={2}
        />
        <Button
          onClick={handleRun}
          disabled={running || !message.trim()}
          size="icon"
          className="h-auto"
        >
          {running ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
        </Button>
      </div>

      {(output || error) && (
        <ScrollArea className="h-64 rounded-md border bg-muted p-4">
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          {output && (
            <pre className="whitespace-pre-wrap text-sm">{output}</pre>
          )}
          <div ref={scrollRef} />
        </ScrollArea>
      )}
    </div>
  );
}
