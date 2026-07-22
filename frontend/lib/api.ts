/**
 * Typed client for the Phase 3 read API (backend/app/api/schemas.py mirrors).
 * All data here is pre-computed and guardrails-validated — the dashboard never
 * calls live inference.
 */

import type { RiskLevel } from "@/lib/viz";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  token: string | null,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// ---- contract mirrors ---------------------------------------------------------

export interface UserOut {
  username: string;
  display_name_th: string;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user: UserOut;
}

export interface SubDistrictOut {
  id: string;
  name_th: string;
  district_th: string;
  province_th: string;
}

export interface Citation {
  chunk_id: string;
  document_id: string | null;
  page: number | null;
  quote_th: string | null;
}

export interface ReasoningStep {
  step_type: "EVIDENCE" | "OBSERVATION" | "INTERPRETATION";
  text_th: string;
  citations: Citation[];
}

export interface RegulationReference {
  regulation_id: string;
  act_name_th: string;
  section_no: string;
  relevance_th: string;
}

export interface RiskFactor {
  factor_type: string;
  score: number;
  weight: number;
  rationale_th: string;
  reasoning_steps: ReasoningStep[];
  citations: Citation[];
}

export interface RiskResult {
  risk_level: RiskLevel;
  overall_score: number;
  factors: RiskFactor[];
  regulation_references: RegulationReference[];
  summary_th: string;
  project_id: string;
  model_id: string;
  prompt_version: string;
  generated_at: string;
}

export interface RiskResultOut {
  result: RiskResult;
  validated_at: string;
}

export interface BidOut {
  bidder_name_th: string;
  bid_amount: number;
  is_winner: boolean;
}

export interface DocumentOut {
  id: string;
  filename: string;
  doc_type: string | null;
  scope: string;
  source: string;
  parse_status: string;
  page_count: number | null;
}

export interface PrecheckFinding {
  name: string;
  status: string;
  detail: string;
  values: Record<string, unknown>;
  severity?: string;
}

export interface ProjectListItem {
  id: string;
  name_th: string;
  fiscal_year: number;
  sub_district: SubDistrictOut;
  budget_total: number | null;
  reference_price: number | null;
  contract_price: number | null;
  procurement_method: string | null;
  risk_level: RiskLevel | null;
  overall_score: number | null;
  precheck_flag_count: number;
}

export interface ProjectListResponse {
  items: ProjectListItem[];
  total: number;
  disclaimer_th: string;
}

export interface ProjectDetail {
  id: string;
  name_th: string;
  fiscal_year: number;
  category_th: string | null;
  status: string;
  sub_district: SubDistrictOut;
  budget_total: number | null;
  reference_price: number | null;
  contract_price: number | null;
  procurement_method: string | null;
  bids: BidOut[];
  documents: DocumentOut[];
  prechecks: PrecheckFinding[];
  prechecks_generated_at: string | null;
  risk: RiskResultOut | null;
  disclaimer_th: string;
}

export interface FeedbackOut {
  id: string;
  project_id: string;
  risk_result_id: string | null;
  text_th: string;
  sentiment: string | null;
  concern_tags: string[];
  created_at: string;
  auditor_username: string;
}

export interface ChunkOut {
  id: string;
  document_id: string;
  chunk_index: number;
  text: string;
  page: number | null;
  language: string;
  document: DocumentOut;
}

export interface RegulationOut {
  regulation_code: string;
  act_name_th: string;
  section_no: string;
  section_title_th: string | null;
  text: string;
}

export interface OverviewTotals {
  project_count: number;
  sub_district_count: number;
  document_count: number;
  budget_total_sum: number;
  scored_project_count: number;
}

export interface HeatmapCell {
  sub_district_id: string;
  sub_district_name_th: string;
  fiscal_year: number;
  project_count: number;
  budget_total: number | null;
  avg_score: number | null;
  worst_risk_level: RiskLevel | null;
}

export interface TopProject {
  id: string;
  name_th: string;
  sub_district_name_th: string;
  fiscal_year: number;
  risk_level: RiskLevel;
  overall_score: number;
}

export interface OverviewResponse {
  totals: OverviewTotals;
  risk_distribution: Partial<Record<RiskLevel, number>>;
  heatmap: HeatmapCell[];
  top_projects: TopProject[];
  disclaimer_th: string;
}

export interface BudgetYearPoint {
  sub_district_id: string;
  sub_district_name_th: string;
  fiscal_year: number;
  project_count: number;
  budget_total: number | null;
  yoy_pct: number | null;
}

export interface ContractorConcentration {
  bidder_name_th: string;
  bids_submitted: number;
  contracts_won: number;
  total_awarded: number | null;
  awarded_share_pct: number | null;
  fiscal_years: number[];
}

export interface TrendsResponse {
  budget_by_year: BudgetYearPoint[];
  contractor_concentration: ContractorConcentration[];
  disclaimer_th: string;
}

// ---- budget items (tracked-item anomaly page) ---------------------------------

export interface ItemSource {
  document_id: string | null;
  filename: string | null;
  page: number | null;
  quote_th: string | null;
}

export interface ItemYear {
  fiscal_year: number;
  project_id: string;
  project_name_th: string;
  quantity: number;
  unit_th: string | null;
  total_amount: number;
  unit_price: number | null;
  unit_price_yoy_pct: number | null;
  pct_of_standard: number | null;
  winner_name: string | null;
  bid_count: number;
  procurement_method: string | null;
  source: ItemSource;
}

export interface StandardPriceOut {
  description_th: string;
  standard_unit_price: number;
  fiscal_year: number | null;
  provenance: string;
  document_id: string | null;
  filename: string | null;
  page: number | null;
}

export interface BudgetItemGroup {
  item_key: string;
  label_th: string;
  sub_district_id: string;
  sub_district_name_th: string;
  years: ItemYear[];
  standard: StandardPriceOut | null;
  findings: PrecheckFinding[];
}

export interface BudgetItemsResponse {
  items: BudgetItemGroup[];
  disclaimer_th: string;
}

// ---- budget-report trends (ภาพรวม budget-by-year chart) ------------------------

export interface BudgetTopItem {
  description_th: string;
  amount: number;
}

export interface BudgetReportYear {
  fiscal_year: number;
  total_budget: number;
  project_count: number;
  budget_yoy_pct: number | null;
  top_items: BudgetTopItem[];
  document_id: string | null;
  document_filename: string | null;
}

export interface BudgetReportGroup {
  sub_district_id: string;
  sub_district_name_th: string;
  years: BudgetReportYear[];
}

export interface BudgetReportTrendsResponse {
  items: BudgetReportGroup[];
  disclaimer_th: string;
}
