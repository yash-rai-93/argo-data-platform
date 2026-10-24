// This module never loads the SDK until analytics consent is granted.
type Consent = "granted" | "denied";
type PredictionSource = "manual" | "preset";
const consentKey = "argo_analytics_consent";
const token = process.env.NEXT_PUBLIC_MIXPANEL_TOKEN;
const apiHost = process.env.NEXT_PUBLIC_MIXPANEL_API_HOST || "https://api.mixpanel.com";
let sdk: (typeof import("mixpanel-browser"))["default"] | undefined;
let pending: Promise<void> | undefined;
let generation = 0;
let dashboardTracked = false;

export function analyticsConfigured(): boolean {
  return Boolean(token);
}
export function readConsent(): Consent | undefined {
  if (typeof window === "undefined") return;
  try {
    const value = localStorage.getItem(consentKey);
    return value === "granted" || value === "denied" ? value : undefined;
  } catch { return; }
}
function permitted(): boolean {
  return readConsent() === "granted" &&
    navigator.doNotTrack !== "1" &&
    !(navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl;
}
export function setConsent(value: Consent): void {
  try { localStorage.setItem(consentKey, value); } catch { return; }
  generation += 1;
  if (value === "denied") {
    try {
      sdk?.opt_out_tracking();
      sdk?.reset();
    } catch { /* Tracking stays blocked by the consent check. */ }
    return;
  }
  void trackDashboard();
}
async function initialize(): Promise<void> {
  if (!token || !permitted()) return;
  if (sdk) { sdk.opt_in_tracking({ track: () => {} }); return; }
  if (pending) return pending;
  const current = generation;
  pending = (async () => {
    const mixpanel = (await import("mixpanel-browser")).default;
    if (current !== generation || !permitted()) return;
    mixpanel.init(token, {
      api_host: apiHost,
      autocapture: false,
      track_pageview: false,
      record_sessions_percent: 0,
      ip: false,
      persistence: "localStorage",
      save_referrer: false,
      store_google: false,
      stop_utm_persistence: true,
      property_blacklist: ["$current_url", "$referrer", "$initial_referrer", "$initial_referring_domain"],
    });
    sdk = mixpanel;
    sdk.opt_in_tracking({ track: () => {} });
  })().catch(() => { /* Analytics failure must never affect the dashboard. */ })
    .finally(() => { pending = undefined; });
  return pending;
}
export async function trackDashboard(): Promise<void> {
  await initialize();
  if (!sdk || !permitted() || dashboardTracked) return;
  dashboardTracked = true;
  try { sdk.track("dashboard_viewed", { platform: "web" }); } catch { /* Non-essential. */ }
}
export async function trackPrediction(source: PredictionSource): Promise<void> {
  await initialize();
  if (!sdk || !permitted()) return;
  try { sdk.track("prediction_completed", { platform: "web", prediction_source: source }); } catch { /* Non-essential. */ }
}
