"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Catalog } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const PROVIDER_ROLES: Record<string, string> = {
  livekit: "WebRTC transport",
  deepgram: "Speech-to-text",
  openai: "LLM (GPT-4.1)",
  cartesia: "English TTS",
  sarvam: "Indian-language TTS",
};

export default function SettingsPage() {
  const [providers, setProviders] = useState<Record<string, boolean>>({});
  const [redis, setRedis] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setProviders(h.providers);
        setRedis(h.redis);
      })
      .catch(() => {});
    api.catalog().then(setCatalog).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Platform configuration and provider status.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Providers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {Object.entries(PROVIDER_ROLES).map(([key, role]) => (
            <div
              key={key}
              className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-4 py-3"
            >
              <div>
                <div className="text-sm font-medium capitalize">{key}</div>
                <div className="text-xs text-muted-foreground">{role}</div>
              </div>
              <Badge variant={providers[key] ? "success" : "muted"}>
                {providers[key] ? "configured" : "no key"}
              </Badge>
            </div>
          ))}
          <div className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-4 py-3">
            <div>
              <div className="text-sm font-medium">Redis</div>
              <div className="text-xs text-muted-foreground">Cache &amp; task queue</div>
            </div>
            <Badge variant={redis ? "success" : "muted"}>
              {redis ? "connected" : "offline"}
            </Badge>
          </div>
          <p className="pt-2 text-xs text-muted-foreground">
            Configure keys in <code>backend/.env</code> (see{" "}
            <code>backend/.env.example</code>). Changes take effect on backend restart.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Supported languages</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {catalog?.languages.map((l) => (
              <Badge key={l.code} variant={l.indian ? "default" : "secondary"}>
                {l.name}
              </Badge>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Voices</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {catalog?.voices.map((v) => (
              <div
                key={v.id}
                className="flex items-center justify-between text-sm"
              >
                <span>{v.name}</span>
                <span className="text-xs text-muted-foreground">
                  {v.provider} · {v.gender}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
