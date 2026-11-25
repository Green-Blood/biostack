"use client";
import { useState, type FormEvent } from "react";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageSwitch } from "@/components/language-switch";
import { useI18n } from "@/lib/i18n/client";

export function AccessGate() {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.status === 401) {
        setError(t("common.gateWrong"));
        return;
      }
      if (!res.ok) {
        setError(t("common.gateError"));
        return;
      }
      window.location.reload();
    } catch {
      setError(t("common.gateError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
      <div className="surface space-y-6 p-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 font-heading text-xl font-semibold">
            <Lock className="size-4 text-primary" aria-hidden />
            BioStack
          </div>
          <LanguageSwitch />
        </div>
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">{t("common.gateTitle")}</h1>
          <p className="text-sm text-muted-foreground">{t("common.gateText")}</p>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("common.gatePlaceholder")}
            aria-label={t("common.gatePlaceholder")}
            autoFocus
            required
            className="w-full rounded-xl border bg-background px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? t("common.gateChecking") : t("common.gateSubmit")}
          </Button>
        </form>
      </div>
    </div>
  );
}
