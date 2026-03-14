import { Bot, Cpu, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { AgentConfig } from "@/lib/types";

/**
 * Read-only preview of a proposed AgentConfig.
 * Shown in the builder chat when the builder produces a config.
 */
export function AgentConfigPreview({ config }: { config: AgentConfig }) {
  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary" />
          <CardTitle className="text-base">{config.name}</CardTitle>
          <Badge variant={config.model_role === "builder" ? "default" : "secondary"}>
            {config.model_role}
          </Badge>
        </div>
        {config.description && (
          <CardDescription>{config.description}</CardDescription>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            System Prompt
          </p>
          <p className="whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
            {config.system_prompt}
          </p>
        </div>

        {config.tools.length > 0 && (
          <>
            <Separator />
            <div>
              <p className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
                <Wrench className="h-3 w-3" />
                Tools
              </p>
              <div className="flex flex-wrap gap-1">
                {config.tools.map((tool) => (
                  <Badge key={tool} variant="outline">
                    {tool}
                  </Badge>
                ))}
              </div>
            </div>
          </>
        )}

        {config.subagents.length > 0 && (
          <>
            <Separator />
            <div>
              <p className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
                <Cpu className="h-3 w-3" />
                Sub-agents
              </p>
              <div className="space-y-2">
                {config.subagents.map((sa) => (
                  <div
                    key={sa.name}
                    className="rounded-md border p-2 text-sm"
                  >
                    <p className="font-medium">{sa.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {sa.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {config.model_override && (
          <>
            <Separator />
            <p className="text-xs text-muted-foreground">
              Model override: <code>{config.model_override}</code>
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
