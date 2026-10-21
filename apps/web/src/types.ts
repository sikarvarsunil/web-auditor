export type Evidence = { type: string; description: string; location?: string | null };
export type Finding = {
  heuristic_id: number; heuristic_name: string; status: 'finding' | 'no_issue_observed' | 'not_observed';
  title: string; evidence: Evidence[]; user_impact: string; severity: 'critical' | 'high' | 'medium' | 'low' | 'not_observed';
  confidence: number; recommendation: string; limitations: string[];
};
export type ReviewedPage = { url: string; title?: string | null; image: string };
export type AuditReport = {
  audit_mode: 'url' | 'screenshot'; source: string; page_title?: string | null; viewport: string;
  summary: string; findings: Finding[]; methodology_note: string; model: string; pages?: ReviewedPage[];
};
