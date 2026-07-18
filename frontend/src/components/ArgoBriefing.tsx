"use client";

import { Rocket } from "lucide-react";

function Accent({ children }: { children: string }) {
  return (
    <span className="font-semibold text-cyan-300 drop-shadow-[0_0_8px_rgba(6,182,212,0.7)]">
      {children}
    </span>
  );
}

export default function ArgoBriefing() {
  return (
    <section className="glass-panel p-6">
      <div className="mb-3 flex items-center gap-2">
        <Rocket className="h-5 w-5 text-cyan-400 drop-shadow-[0_0_8px_rgba(6,182,212,0.8)]" />
        <h2 className="text-lg font-semibold text-slate-100">What is ARGO?</h2>
      </div>
      <p className="leading-relaxed text-slate-300">
        Most enterprise retention tools take months to integrate and require a
        team of data scientists to operate. ARGO is different. It is a{" "}
        <Accent>zero-latency decision engine</Accent> that processes raw customer
        data instantly using <Accent>DuckDB</Accent>, predicts subscription
        cancellations before they happen using an{" "}
        <Accent>XGBoost machine learning model</Accent>, and generates actionable
        business strategies using <Accent>NVIDIA Nemotron reasoning</Accent>. It
        is designed to stop revenue bleeding at the click of a button.
      </p>

      <div className="mt-5 border-l-2 border-cyan-400/40 pl-4">
        <h3 className="mb-2 text-base font-semibold text-cyan-300">
          The Silent Killer: Customer Churn
        </h3>
        <p className="leading-relaxed text-slate-400">
          In the software industry, <Accent>Churn</Accent> refers to a paying
          customer canceling their subscription. It costs a company up to five
          times more to acquire a new customer than to keep an existing one.
          ARGO monitors usage patterns to flag accounts that are losing
          interest, allowing teams to deploy automated save-offers before the
          revenue is permanently lost.
        </p>
      </div>
    </section>
  );
}
