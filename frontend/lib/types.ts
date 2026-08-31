export type AttrState = "MATCH" | "MISMATCH" | "UNKNOWN";
export type SafetyStatus = "PASS" | "BLOCK" | "INSUFFICIENT_EVIDENCE";
export type ReviewStatus =
  | "AUTO_MATCHED"
  | "NEEDS_REVIEW"
  | "INSUFFICIENT_EVIDENCE"
  | "BLOCKED"
  | "APPROVED"
  | "REJECTED";

export interface Attribute {
  value: string | number | null;
  source: string;
  method: "rule" | "derived" | "llm" | "survivorship";
  confidence: number;
  agreement?: string;
  agreement_ratio?: number;
  contested_values?: string[] | null;
  source_record_ids?: number[];
}

export interface Comparison {
  key: string;
  label?: string;
  state: AttrState;
  value_a: string | number | null;
  value_b: string | number | null;
  detail: string;
  equivalence_confidence: number;
  safety_critical?: boolean;
  weight?: number;
}

export interface MatchExplanation {
  score: number;
  semantic: number;
  lexical: number;
  attribute_agreement: number;
  coverage: number;
  weights: { semantic: number; lexical: number; attributes: number };
  comparisons: Comparison[];
  counts: Record<AttrState, number>;
}

export interface SafetyVerdict {
  status: SafetyStatus;
  commodity: string | null;
  blocked_field: string | null;
  blocked_field_label: string | null;
  blocked_values: (string | number | null)[] | null;
  reason: string;
  critical_comparisons: Comparison[];
  unknown_fields: string[];
}

export interface Material {
  id: number;
  cpse_org: string;
  legacy_code: string;
  raw_description: string;
  normalized_description: string;
  attributes: Record<string, Attribute>;
  commodity_type: string | null;
  unspsc_class: string | null;
  created_at: string;
  nmi: string | null;
  match_score: number | null;
  relationship: string | null;
  review_status: ReviewStatus | null;
  review_reason: string | null;
  blocked_field: string | null;
  standardized_description: string | null;
  nmi_siblings?: Material[];
  attribute_schema?: { key: string; label: string }[];
  demo_inventory?: { quantity: number; uom: string; unit_value_inr: number } | null;
}

export interface Candidate {
  rank?: number;
  record_id: number;
  nmi: string | null;
  cpse_org: string;
  legacy_code: string;
  raw_description: string;
  standardized_description: string | null;
  retrieval_source: string;
  score: number;
  explanation: MatchExplanation;
  safety: SafetyVerdict;
  would_merge: boolean;
}

export interface GoldenRecord {
  nmi: string;
  version: number;
  standardized_description: string;
  unspsc_class: string | null;
  commodity_type: string | null;
  attributes: Record<string, Attribute>;
  member_count: number;
  cpse_count?: number;
  created_at: string;
  updated_at: string;
}

export interface CrosswalkMember {
  crosswalk_id: number;
  record_id: number;
  cpse_org: string;
  legacy_code: string;
  raw_description: string;
  normalized_description: string;
  attributes: Record<string, Attribute>;
  match_score: number;
  relationship: string;
  status: string;
  review_status: ReviewStatus | null;
  review_reason: string | null;
  commodity_type: string | null;
}

export interface EvidenceMatrix {
  nmi: string;
  commodity_type: string | null;
  cpses: { record_id: number; cpse_org: string; legacy_code: string; raw_description: string }[];
  rows: {
    key: string;
    label: string;
    safety_critical: boolean;
    cells: {
      record_id: number;
      cpse_org: string;
      legacy_code: string;
      value: string | number | null;
      state: AttrState;
    }[];
    golden: {
      value: string | number | null;
      confidence: number | null;
      agreement: string | null;
      contested_values: string[] | null;
    };
  }[];
}

export interface ReviewItem {
  id: number;
  record_id: number;
  candidate_nmi: string | null;
  candidate_record_id: number | null;
  score: number | null;
  reason: string;
  blocked_field: string | null;
  status: ReviewStatus;
  reviewer: string | null;
  created_at: string;
  reviewed_at: string | null;
  cpse_org: string;
  legacy_code: string;
  raw_description: string;
  commodity_type: string | null;
  candidate_description: string | null;
  evidence_table?: Comparison[];
  safety?: SafetyVerdict;
  attributes?: Record<string, Attribute>;
  candidate_record?: {
    id: number;
    cpse_org: string;
    legacy_code: string;
    raw_description: string;
    attributes: Record<string, Attribute>;
    nmi: string | null;
  } | null;
}

export interface DashboardData {
  totals: {
    total_materials: number;
    golden_records: number;
    crosswalk_links: number;
    pending_review: number;
    blocked_matches: number;
    approved: number;
    rejected: number;
    multi_source_records: number;
    duplicates_removed: number;
  };
  status_breakdown: { status: string; n: number }[];
  commodity_breakdown: { commodity_type: string; materials: number; golden_records: number }[];
  cpse_overview: {
    cpse_org: string;
    materials: number;
    harmonized: number;
    pending: number;
    blocked: number;
    distinct_nmis: number;
    avg_confidence: number | null;
  }[];
  recent_activity: {
    id: number;
    raw_description: string;
    cpse_org: string;
    legacy_code: string;
    nmi: string | null;
    match_score: number | null;
    status: ReviewStatus | null;
    created_at: string;
  }[];
  confidence_histogram: { bucket: number; n: number }[];
  blocked_fields: { blocked_field: string; n: number }[];
  last_job: {
    job_id: string;
    status: string;
    stats: Record<string, unknown>;
    started_at: string;
    finished_at: string | null;
  } | null;
}

export interface GovernanceResult {
  description: string;
  normalized_description?: string;
  commodity_type: string | null;
  commodity_detected: boolean;
  extracted_attributes?: Record<string, Attribute>;
  recommendation: "USE_EXISTING" | "CREATE_NEW" | "REVIEW";
  message: string;
  threshold?: number;
  candidates: {
    nmi: string;
    standardized_description: string;
    matched_record: {
      record_id: number;
      cpse_org: string;
      legacy_code: string;
      raw_description: string;
    };
    cpse_count: number;
    member_count: number;
    score: number;
    explanation: MatchExplanation;
    safety: SafetyVerdict;
  }[];
}
