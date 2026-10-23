// Set NEXT_PUBLIC_API_URL to the Render service origin in the Vercel project.
// The fallback is the container's default port, so `docker run -p 7860:7860`
// works locally with no environment set. NEXT_PUBLIC_ is required: this is
// read in the browser, and Next.js only inlines variables with that prefix.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:7860";
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

// One point on a contributor's survival function: P(T > day), the probability
// they are still contributing after that many days. Produced by scaling a
// Breslow baseline by the Cox model's predicted hazard ratio.
export interface SurvivalPoint {
  day: number;
  survival: number;
}

export interface ChurnPrediction {
  churn_prediction: number;
  probability: number;
  log_odds: number;
  base_log_odds: number;
  shap_attribution: ShapAttribution[];
  top_factors: ShapAttribution[];
  // Cox proportional-hazards output. hazard_ratio is unbounded and relative:
  // 1.0 is the cohort baseline, 2.0 decays twice as fast. median_survival_days
  // is null when the curve never reaches 0.5 inside the 180-day horizon.
  hazard_ratio: number;
  median_survival_days: number | null;
  survival_curve: SurvivalPoint[];
  survival_milestones: SurvivalPoint[];
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

// One row per recorded training iteration. Appended by ml/train_churn.py on
// every run, so the history accumulates from execution rather than editing.
export interface ModelVersion {
  version: string;
  recorded_at: string;
  dataset: string;
  split_strategy: string;
  n_features: number;
  n_rows: number;
  n_train: number;
  n_test: number;
  churn_rate_test: number | null;
  cv_roc_auc: number | null;
  holdout_roc_auc: number | null;
  precision: number | null;
  recall: number | null;
  best_params: string;
  change_summary: string;
  comparable: boolean;
}

export async function fetchModelRegistry(): Promise<ModelVersion[]> {
  return request<ModelVersion[]>("/predict/registry");
}

// Full specification of the deployed model, read from the artifacts on disk
// and the warehouse rather than hardcoded, so it cannot describe a model other
// than the one actually serving predictions.
export interface ModelCard {
  algorithm: string;
  objective: string;
  artifact: string;
  artifact_bytes: number;
  artifact_modified: string | null;
  n_trees: number;
  n_features: number;
  features: { name: string; label: string }[];
  target: string;
  hyperparameters: Record<string, number | string>;
  scale_pos_weight: number | null;
  cv_splits: number | null;
  cv_roc_auc: number | null;
  decision_threshold: number;
  explainer: string;
  data: {
    source: string;
    window_start: string;
    window_end: string;
    source_rows: number;
    repos: number;
    cohort_rows: number;
    cohort_churn_rate: number;
    eligibility: string;
    observation_window: string;
    target_window: string;
  };
}

export async function fetchModelCard(): Promise<ModelCard> {
  return request<ModelCard>("/predict/model-card");
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

// One row of the triage queue, scored live by the Cox survival model.
// median_survival_days is null when the curve never reaches 50% inside the
// 180-day horizon -- the contributor has no projected lapse date, which is a
// real answer, not a missing value.
export interface CustomerRisk {
  contributor: string;
  primary_repo: string;
  tenure_days: number;
  total_events: number;
  days_since_last_event: number;
  hazard_ratio: number;
  median_survival_days: number | null;
  survival_curve: SurvivalPoint[];
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
