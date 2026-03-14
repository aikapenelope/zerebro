import Link from "next/link";
import { Bot, MessageSquare, Server } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Landing / dashboard page. Shows quick-access links to the main sections.
 * The agent list is loaded on the dashboard page within the (dashboard) group.
 */
export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight">Zerebro</h1>
        <p className="mt-2 text-muted-foreground">
          Self-hosted agent builder platform
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Link href="/agents">
          <Button variant="outline" className="h-24 w-48 flex-col gap-2">
            <Bot className="h-6 w-6" />
            <span>Agents</span>
          </Button>
        </Link>

        <Link href="/builder">
          <Button variant="outline" className="h-24 w-48 flex-col gap-2">
            <MessageSquare className="h-6 w-6" />
            <span>Builder</span>
          </Button>
        </Link>

        <Link href="/mcp">
          <Button variant="outline" className="h-24 w-48 flex-col gap-2">
            <Server className="h-6 w-6" />
            <span>MCP Servers</span>
          </Button>
        </Link>
      </div>
    </div>
  );
}
