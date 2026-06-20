import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { AgentForm } from "@/components/agent-form";

export default function NewAgentPage() {
  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/agents"
          className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" /> Agents
        </Link>
        <h1 className="text-2xl font-semibold">Create agent</h1>
        <p className="text-sm text-muted-foreground">
          Configure your agent, then test it live in the browser.
        </p>
      </div>
      <AgentForm mode="create" />
    </div>
  );
}
