"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Loader2, Trash2, UploadCloud, CheckCircle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";

interface KnowledgeDoc {
  id: string;
  filename: string;
  file_type: string;
  chunk_count: number;
  status: "processing" | "ready" | "error";
  error_message: string | null;
}

async function fetchDocs(agentId: string): Promise<KnowledgeDoc[]> {
  const res = await fetch(`${BASE}/agents/${agentId}/knowledge`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function uploadDoc(agentId: string, file: File): Promise<KnowledgeDoc> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/agents/${agentId}/knowledge`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

async function deleteDoc(agentId: string, docId: string): Promise<void> {
  const res = await fetch(`${BASE}/agents/${agentId}/knowledge/${docId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}

export function KnowledgeBase({ agentId }: { agentId: string }) {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchDocs(agentId)
      .then(setDocs)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [agentId]);

  useEffect(() => { load(); }, [load]);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setError(null);
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        const doc = await uploadDoc(agentId, file);
        setDocs((prev) => [doc, ...prev]);
      } catch (e) {
        setError(`${file.name}: ${String(e)}`);
      }
    }
    setUploading(false);
    // Refresh to pick up final processing status
    setTimeout(load, 2000);
  }

  async function handleDelete(docId: string) {
    try {
      await deleteDoc(agentId, docId);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
    } catch (e) {
      setError(String(e));
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  }

  const totalChunks = docs.filter((d) => d.status === "ready").reduce((s, d) => s + d.chunk_count, 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium">Knowledge base</h3>
          <p className="text-xs text-muted-foreground">
            Upload PDF, DOCX, or TXT files. The agent will search them automatically when callers ask questions.
          </p>
        </div>
        {totalChunks > 0 && (
          <span className="text-xs text-muted-foreground">{totalChunks} chunks indexed</span>
        )}
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 transition-colors",
          dragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-secondary/40"
        )}
      >
        {uploading ? (
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        ) : (
          <UploadCloud className="h-8 w-8 text-muted-foreground" />
        )}
        <p className="text-sm text-muted-foreground">
          {uploading ? "Uploading & indexing…" : "Drop files here or click to browse"}
        </p>
        <p className="text-xs text-muted-foreground/60">PDF · DOCX · TXT · MD — max 50 MB each</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {error && (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
      )}

      {/* Document list */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading documents…
        </div>
      ) : docs.length === 0 ? (
        <p className="text-center text-sm text-muted-foreground py-4">No documents uploaded yet.</p>
      ) : (
        <div className="space-y-2">
          {docs.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
            >
              <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{doc.filename}</p>
                <p className="text-xs text-muted-foreground">
                  {doc.file_type.toUpperCase()}
                  {doc.status === "ready" && ` · ${doc.chunk_count} chunks`}
                  {doc.status === "processing" && " · indexing…"}
                  {doc.status === "error" && doc.error_message && ` · ${doc.error_message}`}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {doc.status === "ready" && <CheckCircle className="h-4 w-4 text-emerald-500" />}
                {doc.status === "processing" && <Loader2 className="h-4 w-4 animate-spin text-amber-400" />}
                {doc.status === "error" && <AlertCircle className="h-4 w-4 text-destructive" />}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  onClick={() => handleDelete(doc.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
