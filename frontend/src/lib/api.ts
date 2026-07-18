const BASE_URL = "http://127.0.0.1:8000/api/v1";

export interface ExecutiveMetrics {
  mrr: number;
  arr: number;
  dau: number;
}

export interface IntelligenceSummary {
  summary: string;
}

export interface ChurnFeatures {
  total_sessions: number;
  avg_session_duration: number;
  account_age_days: number;
}

export interface ChurnPrediction {
  churn_prediction: number;
  probability: number;
}

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
