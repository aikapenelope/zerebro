import Link from "next/link";
import { Bot, Clock, Cpu, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AgentConfig } from "@/lib/types";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AgentCard({ agent }: { agent: AgentConfig }) {
  return (
    <Link href={`/agents/${agent.id}`}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">{agent.name}</CardTitle>
            </div>
            <Badge variant={agent.model_role === "builder" ? "default" : "secondary"}>
              {agent.model_role}
            </Badge>
          </div>
          {agent.description && (
            <CardDescription className="line-clamp-2">
              {agent.description}
            </CardDescription>
          )}
        </CardHeader>

        <CardContent>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {agent.tools.length > 0 && (
              <span className="flex items-center gap-1">
                <Wrench className="h-3 w-3" />
                {agent.tools.length} tool{agent.tools.length !== 1 && "s"}
              </span>
            )}
            {agent.subagents.length > 0 && (
              <span className="flex items-center gap-1">
                <Cpu className="h-3 w-3" />
                {agent.subagents.length} sub-agent
                {agent.subagents.length !== 1 && "s"}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDate(agent.created_at)}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
