"use client";

import { useEffect, useState } from "react";
import { analyticsConfigured, readConsent, setConsent, trackDashboard } from "@/lib/analytics";

export default function AnalyticsConsent() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!analyticsConfigured()) return;
    if (readConsent() === undefined) {
      // Run after hydration so the server and first client render agree.
      const timer = window.setTimeout(() => setOpen(true), 0);
      return () => window.clearTimeout(timer);
    }
    void trackDashboard();
  }, []);
  if (!analyticsConfigured()) return null;
  function choose(granted: boolean) {
    setConsent(granted ? "granted" : "denied");
    setOpen(false);
  }
  return (
    <div className="fixed bottom-4 left-4 right-4 z-[100] mx-auto max-w-xl">
      {open ? (
        <section aria-label="Analytics preferences" className="rounded-xl border border-slate-700 bg-slate-950 p-4 text-sm text-slate-200 shadow-xl">
          <p>Allow anonymous usage analytics? We count dashboard visits and completed predictions to improve Argo. We do not send prediction inputs or contributor identities. Your browser privacy signals are respected.</p>
          <div className="mt-3 flex flex-wrap gap-3">
            <button type="button" onClick={() => choose(true)} className="rounded border border-slate-500 px-3 py-2">Accept analytics</button>
            <button type="button" onClick={() => choose(false)} className="rounded border border-slate-500 px-3 py-2">Decline analytics</button>
          </div>
        </section>
      ) : (
        <button type="button" onClick={() => setOpen(true)} className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-300">Analytics preferences</button>
      )}
    </div>
  );
}
