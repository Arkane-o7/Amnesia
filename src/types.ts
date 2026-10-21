export type Status =
  "active" | "superseded" | "invalid" | "unresolved" | "expired" | "future";
export type Decision = {
  id?: string;
  event_id?: string;
  label: string;
  reason: string;
  fact_id: string;
  existing_id: string | null;
  subject?: string;
  relation?: string;
  value?: string;
  created_at?: string;
};
export type Fact = {
  id: string;
  subject_id: string;
  subject: string;
  relation: string;
  object_id: string;
  value: string;
  valid_from: string;
  valid_until: string | null;
  observed_at: string;
  evidence: string;
  event_id: string;
  confidence: number;
  status: Status;
  effective_status: Status;
  superseded_by: string | null;
  evidence_count: number;
  scope?: string;
  intent?: string;
  history?: { status: string; observed_at: string; reason: string }[];
};
export type Candidate = Fact & {
  score: number;
  components: Record<string, number>;
  eligible: boolean;
};
export type QueryResult = {
  question: string;
  answer: string;
  answer_value: string | null;
  method: string;
  memory_needed: boolean;
  gate_bypassed: boolean;
  candidates: Candidate[];
  retrieved: Candidate[];
  used_ids: string[];
  latency_ms: number;
  context_tokens_estimate: number;
  as_of: string;
  semantic_engine: string;
  answer_engine: string;
  answer_status?: string;
  used_event_ids?: string[];
  graph_engine?: string;
  historical?: boolean;
};
export type IngestResult = {
  assertions: number;
  decisions: Decision[];
  unsupported: string[];
  provider: string;
  latency_ms: number;
  pipeline?: { extraction_ms: number; reconciliation_ms: number };
};
export type MemoryEvent = {
  id: string;
  session_id: string;
  role: "user" | "query";
  text: string;
  observed_at: string;
  result: IngestResult | QueryResult;
};
export type Workspace = { id: string; name: string; created_at: string };
export type Session = { id: string; name: string; created_at: string };
export type State = {
  workspace: Workspace;
  sessions: Session[];
  facts: Fact[];
  entities: { id: string; name: string }[];
  events: MemoryEvent[];
  decisions: Decision[];
  as_of: string;
};
export type Scenario = {
  id: string;
  name: string;
  description: string;
  turns: string[];
  question: string;
};
export type Metric = {
  answer_accuracy: number;
  smer: number;
  recall_at_5: number;
  mrr: number;
  mean_latency_ms: number;
  p95_latency_ms: number;
  mean_context_tokens_estimate: number;
  instances: number;
  evolved_questions: number;
  stale_answers: number;
};
export type Evaluation = {
  artifact_origin?: string;
  suite?: string;
  title?: string;
  engine?: { provider: string; chat_model: string; embedding_model: string };
  retrieval_k?: number;
  measured_live_calls?: number;
  cache_hits?: number;
  actual_input_tokens?: number;
  actual_output_tokens?: number;
  count: number;
  seed: number;
  generated_at: string;
  duration_ms: number;
  limitations: string[];
  metrics: Record<string, Metric>;
  extraction: { precision: number; recall: number; f1: number };
  reconciliation: {
    accuracy: number;
    macro_f1: number;
    per_label: Record<
      string,
      { precision: number; recall: number; f1: number; support: number }
    >;
    confusion: Record<string, Record<string, number>>;
  };
  false_invalidation: { rate: number; retired: number; considered: number };
  gate: { precision: number; recall: number; f1: number } | null;
  categories: Record<string, Record<string, { accuracy: number; n: number }>>;
  splits: Record<string, Record<string, { accuracy: number; n: number }>>;
  failures: {
    id: string;
    category: string;
    turns: string[];
    question: string;
    expected: string | null;
    actual: string | null;
    unsupported?: string[];
    error?: string | null;
    answer?: string;
  }[];
};
export const relations: Record<string, string> = {
  lives_in: "lives in",
  prefers: "prefers",
  works_at: "works at",
  leads: "leads",
  owns: "uses",
  plans_to: "plans to visit",
  birthday: "birthday",
  meeting_day: "meeting on",
  name: "is named",
  temporary_location: "visiting",
  likes: "likes",
  studies_at: "studies at",
  located_in: "is based in",
  related_to: "is related to",
  role: "has role",
};
export const methods: Record<string, string> = {
  context: "Full conversation context",
  hybrid: "Amnesia hybrid",
  vector: "Vector similarity",
  graph: "Graph only",
  recent: "Recent assertions",
  hybrid_no_temporal: "Without temporal policy",
  hybrid_no_graph: "Without graph score",
};
export const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
export const date = (s: string) =>
  new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short" });
