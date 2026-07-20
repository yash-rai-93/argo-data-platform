// Prefer the deployed API host, falling back to the local dev server.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const BASE_URL = `${API_BASE_URL}/api/v1`;

export interface ExecutiveMetrics {
  active_contributors: number;
  pr_throughput: number;
  retention_rate: number;
}

export interface IntelligenceSummary {
  summary: string;
  reasoning?: string;
}

// Observation-window behaviour for one GitHub contributor.
// Mirrors FEATURE_COLUMNS in ml/feature_extractor.py exactly: 16 numeric
// features, same order, same names as the ChurnPredictionRequest schema.
export interface ChurnFeatures {
  total_events: number;
  distinct_repos: number;
  active_days: number;
  commit_events: number;
  pull_request_events: number;
  issue_events: number;
  comment_events: number;
  engagement_events: number;
  release_events: number;
  weekend_ratio: number;
  events_per_active_day: number;
  tenure_days: number;
  days_since_last_event: number;
  // Trajectory features. velocity_30d is bounded [0, 1]; deceleration_score is
  // a signed raw event delta; deceleration_ratio is bounded [-1, 1].
  velocity_30d: number;
  deceleration_score: number;
  deceleration_ratio: number;
}

// Signed log-odds contribution of a single feature to one prediction.
// Positive pushes toward churn, negative pushes toward retention.
export interface ShapAttribution {
  feature: string;
  contribution: number;
}

export interface ChurnPrediction {
  churn_prediction: number;
  probability: number;
  log_odds: number;
  base_log_odds: number;
  shap_attribution: ShapAttribution[];
  top_factors: ShapAttribution[];
}

// Scored temporal holdout, served once so the threshold slider can recompute a
// confusion matrix client-side without further round trips.
export interface ThresholdHoldout {
  n: number;
  positive_rate: number;
  y_true: number[];
  y_prob: number[];
}

export async function fetchThresholdHoldout(): Promise<ThresholdHoldout> {
  return request<ThresholdHoldout>("/predict/simulate/threshold");
}

// dbt build metadata, parsed straight from run_results.json by
// etl/ingest_dbt_artifacts.py. Nothing here is hand-maintained.
export interface DbtTestResult {
  name: string;
  status: string;
  failures: number;
  execution_time: number;
}

export interface DbtModelResult {
  name: string;
  resource_type: string;
  materialization: string | null;
  status: string;
  execution_time: number;
  row_count: number;
  file_path: string | null;
}

export interface GovernanceHealth {
  status: string;
  invocation_id?: string;
  run_at?: string;
  dbt_version?: string;
  elapsed_seconds?: number;
  tests_passed?: number;
  tests_total?: number;
  tests?: DbtTestResult[];
  models?: DbtModelResult[];
  source?: {
    table: string;
    row_count: number;
    window_start: string;
    window_end: string;
  };
  detail?: string;
}

export async function fetchGovernanceHealth(): Promise<GovernanceHealth> {
  return request<GovernanceHealth>("/metrics/governance/health");
}

export interface CustomerRisk {
  contributor: string;
  primary_repo: string;
  tenure_days: number;
  total_events: number;
  days_since_last_event: number;
  risk_score: number;
}

export interface TrendMetric {
  name: string;
  value: number;
}

const FALLBACK_TREND: TrendMetric[] = [];

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

export async function fetchContributorTrend(): Promise<TrendMetric[]> {
  try {
    return await request<TrendMetric[]>("/metrics/trend");
  } catch {
    return FALLBACK_TREND;
  }
}

// Empty arrays, not invented numbers. A sparkline that silently falls back to
// fabricated data is worse than one that renders nothing.
export async function fetchContributorsSparkline(): Promise<number[]> {
  try {
    return await request<number[]>("/metrics/contributors/sparkline");
  } catch {
    return [];
  }
}

export async function fetchThroughputSparkline(): Promise<number[]> {
  try {
    return await request<number[]>("/metrics/throughput/sparkline");
  } catch {
    return [];
  }
}

export async function fetchRetentionSparkline(): Promise<number[]> {
  try {
    return await request<number[]>("/metrics/retention/sparkline");
  } catch {
    return [];
  }
}
