// Prefer the deployed API host, falling back to the local dev server.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const BASE_URL = `${API_BASE_URL}/api/v1`;

export interface ExecutiveMetrics {
  mrr: number;
  arr: number;
  dau: number;
}

export interface IntelligenceSummary {
  summary: string;
  reasoning?: string;
}

export interface ChurnFeatures {
  total_sessions: number;
  avg_session_duration: number;
  account_age_days: number;
}

export interface ShapAttribution {
  feature: string;
  impact: number;
}

export interface ChurnPrediction {
  churn_prediction: number;
  probability: number;
  shap_attribution: ShapAttribution[];
}

export interface CustomerRisk {
  user_id: string;
  account_age_days: number;
  total_sessions: number;
  churn_probability: number;
}

export interface TrendMetric {
  name: string;
  mrr: number;
}

const FALLBACK_TREND: TrendMetric[] = [
  { name: "Feb", mrr: 420 },
  { name: "Mar", mrr: 520 },
  { name: "Apr", mrr: 610 },
  { name: "May", mrr: 680 },
  { name: "Jun", mrr: 740 },
  { name: "Jul", mrr: 880 },
];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(
      `Request to ${path} failed: ${response.status} ${response.statusText}`,
    );
  }
  return (await response.json()) as T;
}

export async function fetchExecutiveMetrics(): Promise<ExecutiveMetrics> {
  return request<ExecutiveMetrics>("/metrics/executive");
}

export async function fetchIntelligenceSummary(): Promise<IntelligenceSummary> {
  return request<IntelligenceSummary>("/intelligence/summary");
}

export async function predictChurn(
  features: ChurnFeatures,
): Promise<ChurnPrediction> {
  return request<ChurnPrediction>("/predict/churn", {
    method: "POST",
    body: JSON.stringify(features),
  });
}

export async function fetchRiskList(): Promise<CustomerRisk[]> {
  return request<CustomerRisk[]>("/customers/risk");
}

export async function fetchMrrTrend(): Promise<TrendMetric[]> {
  try {
    return await request<TrendMetric[]>("/metrics/trend");
  } catch {
    return FALLBACK_TREND;
  }
}

const FALLBACK_DAU_SPARK = [3, 5, 4, 6, 5, 7];
const FALLBACK_ARR_SPARK = [5040, 6240, 7320, 8160, 8880, 10560];

export async function fetchDauSparkline(): Promise<number[]> {
  try {
    return await request<number[]>("/metrics/dau/sparkline");
  } catch {
    return FALLBACK_DAU_SPARK;
  }
}

export async function fetchArrSparkline(): Promise<number[]> {
  try {
    return await request<number[]>("/metrics/arr/sparkline");
  } catch {
    return FALLBACK_ARR_SPARK;
  }
}
