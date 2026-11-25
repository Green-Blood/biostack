"use client";
import { Check, ImagePlus, MessageSquarePlus, Sparkles, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/client";
import { getJson, postStream, sendJson } from "@/lib/request";
import type { ChatAction, ChatAnswer, ChatMessageItem, ChatThreadDetail, ChatThreadSummary, ChatUsage } from "@/lib/types";

export function AskPanel() {
  const { t, formatNumber } = useI18n();
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [latestUsage, setLatestUsage] = useState<ChatUsage | null>(null);
  const [actionBusy, setActionBusy] = useState<Record<string, boolean>>({});

  const [question, setQuestion] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [streamed, setStreamed] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const switchThread = useCallback(async (id: number) => {
    setError("");
    setCurrentThreadId(id);
    try {
      const detail = await getJson<ChatThreadDetail>(`chat/threads/${id}`);
      setMessages(detail.messages || []);
      setLatestUsage(null);
    } catch (err) {
      setError((err as Error).message || t("ask.failed"));
    }
  }, [t]);

  function newChat() {
    setCurrentThreadId(null);
    setMessages([]);
    setLatestUsage(null);
    setQuestion("");
    setPhoto(null);
    setError("");
  }

  useEffect(() => {
    let cancelled = false;
    getJson<ChatThreadSummary[]>("chat/threads?channel=web")
      .then(async (list) => {
        if (cancelled) return;
        setThreads(list);
        if (list.length > 0) {
          await switchThread(list[0].id);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [switchThread]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages.length, busy]);

  async function deleteCurrentThread() {
    if (!currentThreadId) return;
    if (!window.confirm(t("ask.confirmDeleteChat"))) return;
    setError("");
    const deletingId = currentThreadId;
    try {
      await sendJson(`chat/threads/${deletingId}`, "DELETE");
      const remaining = threads.filter((th) => th.id !== deletingId);
      setThreads(remaining);
      if (remaining.length > 0) {
        await switchThread(remaining[0].id);
      } else {
        newChat();
      }
    } catch (err) {
      setError((err as Error).message || t("ask.failed"));
    }
  }

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const asked = question.trim();
    if (!asked || busy) return;
    setBusy(true);
    setError("");
    setStreamed("");

    const form = new FormData();
    form.append("question", asked);
    form.append("channel", "web");
    if (currentThreadId !== null) {
      form.append("thread_id", String(currentThreadId));
    }
    if (photo) {
      form.append("image", photo);
    }

    try {
      const res = await postStream<ChatAnswer>("chat/ask-stream", form, (d) => setStreamed((prev) => prev + d));
      const newThreadId = res.thread_id ?? currentThreadId;
      setCurrentThreadId(newThreadId);
      setLatestUsage(res.usage);
      setQuestion("");
      setPhoto(null);

      if (newThreadId) {
        const detail = await getJson<ChatThreadDetail>(`chat/threads/${newThreadId}`);
        setMessages(detail.messages || []);
        const list = await getJson<ChatThreadSummary[]>("chat/threads?channel=web");
        setThreads(list);
      }
    } catch (err) {
      setError((err as Error).message || t("ask.failed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleAction(messageId: number, actionId: string, type: "confirm" | "dismiss") {
    const key = `${messageId}-${actionId}`;
    setActionBusy((prev) => ({ ...prev, [key]: true }));
    try {
      const updated = await sendJson<ChatAction>(`chat/messages/${messageId}/actions/${actionId}/${type}`, "POST");
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== messageId) return msg;
          return {
            ...msg,
            actions: msg.actions.map((act) => (act.id === actionId ? updated : act)),
          };
        }),
      );
    } catch (err) {
      setError((err as Error).message || t("ask.failed"));
    } finally {
      setActionBusy((prev) => ({ ...prev, [key]: false }));
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div className="flex items-center gap-2">
          {threads.length > 0 && (
            <select
              aria-label={t("ask.threadsLabel")}
              value={currentThreadId ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                if (!val) newChat();
                else void switchThread(Number(val));
              }}
              className="h-9 rounded-md border bg-background px-3 py-1 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {currentThreadId === null && <option value="">{t("ask.newChat")}</option>}
              {threads.map((th) => (
                <option key={th.id} value={th.id}>
                  {th.title || `Chat #${th.id}`}
                </option>
              ))}
            </select>
          )}
          <Button type="button" variant="outline" size="sm" onClick={newChat}>
            <MessageSquarePlus aria-hidden className="size-4" /> {t("ask.newChat")}
          </Button>
        </div>
        {currentThreadId !== null && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void deleteCurrentThread()}
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2 aria-hidden className="size-4" /> {t("ask.deleteChat")}
          </Button>
        )}
      </div>

      {messages.length > 0 && (
        <section aria-live="polite" aria-label={t("ask.answerTitle")} className="space-y-4">
          {messages.map((m) => (
            <div key={m.id} className="space-y-3">
              {m.role === "user" ? (
                <div className="ml-auto w-fit max-w-[85%] whitespace-pre-wrap rounded-2xl bg-accent px-4 py-2.5 text-sm">
                  <span className="eyebrow mb-1 block">{t("ask.youLabel")}</span>
                  {m.text}
                  {m.image_url && (
                    <div className="mt-2">
                      {/* eslint-disable-next-line @next/next/no-img-element -- user uploaded photo served by API */}
                      <img
                        src={m.image_url}
                        alt={t("ask.imageAlt")}
                        className="max-h-48 rounded-lg border object-cover"
                      />
                    </div>
                  )}
                </div>
              ) : (
                <div className="max-w-prose space-y-3 rounded-2xl border bg-card/60 p-4">
                  <span className="eyebrow block">{t("ask.aiLabel")}</span>
                  <div className="space-y-3 whitespace-pre-wrap leading-relaxed">{m.text}</div>
                  {m.actions && m.actions.length > 0 && (
                    <div className="space-y-2 border-t pt-3">
                      {m.actions.map((act) => {
                        const isPending = act.status === "pending";
                        const actPendingLoading = !!actionBusy[`${m.id}-${act.id}`];
                        return (
                          <div
                            key={act.id}
                            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-background/50 p-3 text-sm"
                          >
                            <span className="font-medium">{act.label}</span>
                            {isPending ? (
                              <div className="flex items-center gap-2">
                                <Button
                                  type="button"
                                  size="sm"
                                  disabled={actPendingLoading}
                                  onClick={() => void handleAction(m.id, act.id, "confirm")}
                                >
                                  <Check className="size-3.5" aria-hidden /> {t("ask.confirmAction")}
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  disabled={actPendingLoading}
                                  onClick={() => void handleAction(m.id, act.id, "dismiss")}
                                >
                                  <X className="size-3.5" aria-hidden /> {t("ask.dismissAction")}
                                </Button>
                              </div>
                            ) : (
                              <span
                                className={`text-xs ${
                                  act.status === "done"
                                    ? "text-positive"
                                    : act.status === "failed"
                                    ? "text-outrange"
                                    : "text-muted-foreground"
                                }`}
                              >
                                {act.status === "done" && (act.result || t("ask.actionConfirmed"))}
                                {act.status === "dismissed" && t("ask.actionDismissed")}
                                {act.status === "failed" && (act.result ? `${t("ask.actionFailed")}: ${act.result}` : t("ask.actionFailed"))}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          {latestUsage && (
            <p className="tnum text-xs text-muted-foreground">
              {t("ask.usage", {
                input: formatNumber(latestUsage.input_tokens),
                cached: formatNumber(latestUsage.cached_tokens),
                output: formatNumber(latestUsage.output_tokens),
              })}
            </p>
          )}
        </section>
      )}

      {busy && !streamed && <div role="status" className="skeleton h-24 rounded-2xl" aria-label={t("ask.asking")} />}
      {busy && streamed && <p className="whitespace-pre-wrap rounded-2xl bg-card px-4 py-2.5 text-sm">{streamed}</p>}
      {error && (
        <p role="alert" className="text-sm text-outrange">
          {error}
        </p>
      )}

      <form onSubmit={send} className="space-y-3">
        <label htmlFor="ask-question" className="text-sm font-medium">
          {messages.length ? t("ask.followUpPh") : t("ask.questionLabel")}
        </label>
        <Textarea
          id="ask-question"
          rows={messages.length ? 2 : 4}
          value={question}
          maxLength={4000}
          placeholder={messages.length ? t("ask.followUpPh") : t("ask.questionPh")}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          className="rounded-2xl"
        />
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/heic,.heic"
          className="sr-only"
          tabIndex={-1}
          aria-label={t("ask.attach")}
          onChange={(e) => {
            setPhoto(e.target.files?.[0] ?? null);
            e.target.value = "";
          }}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" disabled={busy || !question.trim()}>
            <Sparkles aria-hidden /> {busy ? t("ask.asking") : t("ask.send")}
          </Button>
          {photo ? (
            <span className="inline-flex items-center gap-2 rounded-full border bg-card/60 py-1 pl-3 pr-1 text-sm">
              <span className="max-w-[14rem] truncate">{photo.name}</span>
              <button
                type="button"
                aria-label={t("ask.removePhoto")}
                onClick={() => setPhoto(null)}
                className="rounded-full p-1.5 hover:bg-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <X className="size-4" aria-hidden />
              </button>
            </span>
          ) : (
            <Button type="button" variant="outline" size="lg" onClick={() => fileRef.current?.click()}>
              <ImagePlus aria-hidden /> {t("ask.attach")}
            </Button>
          )}
          {messages.length > 0 && (
            <Button type="button" variant="ghost" size="lg" onClick={newChat}>
              <MessageSquarePlus aria-hidden /> {t("ask.newChat")}
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{t("ask.enterHint")}</p>
        {!photo && <p className="text-xs text-muted-foreground">{t("ask.photoHint")}</p>}
        <p className="max-w-prose text-xs text-muted-foreground">{t("ask.privacy")}</p>
      </form>
      <div ref={endRef} />
    </div>
  );
}