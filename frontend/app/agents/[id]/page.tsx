"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, Mic } from "lucide-react";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { AgentForm } from "@/components/agent-form";
import { KnowledgeBase } from "@/components/knowledge-base";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function EditAgentPage() {
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [prompt, setPrompt] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getAgent(id).then(setAgent).catch((e) => setError(String(e)));
  }, [id]);

  function loadPreview() {
    api
      .promptPreview(id)
      .then((p) => setPrompt(p.system_prompt))
      .catch((e) => setPrompt(`Could not render preview: ${e}`));
  }

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!agent) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link
            href="/agents"
            className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ChevronLeft className="h-4 w-4" /> Agents
          </Link>
          <h1 className="text-2xl font-semibold">{agent.name}</h1>
          <p className="text-sm text-muted-foreground">Configure and inspect this agent.</p>
        </div>
        <Button asChild>
          <Link href={`/agents/${id}/test`}>
            <Mic className="h-4 w-4" /> Test voice
          </Link>
        </Button>
      </div>

      <Tabs defaultValue="configure">
        <TabsList>
          <TabsTrigger value="configure">Configure</TabsTrigger>
          <TabsTrigger value="prompt" onClick={loadPreview}>
            Prompt preview
          </TabsTrigger>
        </TabsList>

        <TabsContent value="configure" className="space-y-6">
          <AgentForm mode="edit" initial={agent} onSaved={setAgent} />

          {/* Knowledge base — always visible, upload is optional */}
          <Card>
            <CardHeader>
              <CardTitle>Knowledge base</CardTitle>
            </CardHeader>
            <CardContent>
              <KnowledgeBase agentId={id} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="prompt">
          <Card>
            <CardContent className="pt-6">
              <p className="mb-3 text-sm text-muted-foreground">
                Fully-assembled system prompt (global → business → agent → tone →
                language → capabilities). This is what the LLM receives each turn.
              </p>
              <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg bg-background/60 p-4 text-xs leading-relaxed text-foreground/90">
                {prompt || "Click the tab to render…"}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
