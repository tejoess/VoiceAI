"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, Mic, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () =>
    api
      .listAgents()
      .then(setAgents)
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  async function remove(id: string, name: string) {
    if (!confirm(`Delete agent "${name}"? This cannot be undone.`)) return;
    await api.deleteAgent(id);
    setAgents((a) => a.filter((x) => x.id !== id));
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Agents</h1>
          <p className="text-sm text-muted-foreground">Manage your voice agents.</p>
        </div>
        <Button asChild>
          <Link href="/agents/new">
            <Plus className="h-4 w-4" /> Create agent
          </Link>
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : agents.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Bot className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No agents yet.</p>
            <Button asChild>
              <Link href="/agents/new">Create your first agent</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {agents.map((a) => (
            <Card key={a.id}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/15">
                      <Bot className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <div className="font-medium">{a.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {a.languages.map((l) => l.toUpperCase()).join(" · ")}
                      </div>
                    </div>
                  </div>
                  <Badge variant={a.is_active ? "success" : "muted"}>
                    {a.is_active ? "active" : "paused"}
                  </Badge>
                </div>
                {a.description && (
                  <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">
                    {a.description}
                  </p>
                )}
                <div className="mt-4 flex gap-2">
                  <Button asChild size="sm" variant="default" className="flex-1">
                    <Link href={`/agents/${a.id}/test`}>
                      <Mic className="h-4 w-4" /> Test
                    </Link>
                  </Button>
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/agents/${a.id}`}>
                      <Pencil className="h-4 w-4" /> Edit
                    </Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => remove(a.id, a.name)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
