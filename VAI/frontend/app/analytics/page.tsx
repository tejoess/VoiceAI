"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AnalyticsSummary, CallSession } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [sessions, setSessions] = useState<CallSession[]>([]);

  useEffect(() => {
    api.analytics().then(setSummary).catch(() => {});
    api.listSessions().then(setSessions).catch(() => {});
  }, []);

  const langEntries = Object.entries(summary?.sessions_by_language ?? {});
  const maxLang = Math.max(1, ...langEntries.map(([, n]) => n));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Analytics</h1>
        <p className="text-sm text-muted-foreground">
          Test-session activity across your agents.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "Agents", value: summary?.agents ?? "—" },
          { label: "Sessions", value: summary?.total_sessions ?? "—" },
          { label: "Avg turns", value: summary?.avg_turns ?? "—" },
          {
            label: "Avg duration",
            value: summary ? `${summary.avg_duration_seconds}s` : "—",
          },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="pt-6">
              <div className="text-2xl font-semibold">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>By language</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {langEntries.length === 0 && (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            )}
            {langEntries.map(([lang, n]) => (
              <div key={lang}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="uppercase">{lang}</span>
                  <span className="text-muted-foreground">{n}</span>
                </div>
                <div className="h-2 rounded-full bg-secondary">
                  <div
                    className="h-2 rounded-full bg-primary"
                    style={{ width: `${(n / maxLang) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent sessions</CardTitle>
          </CardHeader>
          <CardContent>
            {sessions.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No sessions recorded yet.
              </p>
            ) : (
              <div className="space-y-2">
                {sessions.slice(0, 12).map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-3 py-2 text-sm"
                  >
                    <div className="flex items-center gap-3">
                      <Badge variant="outline">{s.language.toUpperCase()}</Badge>
                      <span className="text-muted-foreground">{s.channel}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>{s.turn_count} turns</span>
                      <Badge
                        variant={s.status === "completed" ? "success" : "muted"}
                      >
                        {s.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
