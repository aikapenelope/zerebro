import Link from "next/link";
import { ArrowLeft, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Twin mode layout -- clean, full-width for the conversational builder.
 * Minimal chrome: just a back button and branding.
 */
export default function TwinLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-14 items-center gap-4 border-b px-4">
        <Link href="/">
          <Button variant="ghost" size="sm" className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5" />
          <span className="font-semibold">Zerebro Builder</span>
        </div>
      </header>
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
