export interface Recipient {
  matched: boolean;
  to: string[];
  cc: string[];
  malos: string[];
  unternehmen: string | null;
  warnings: string[];
}

export interface DocResult {
  filename: string;
  doc_id: string | null;
  category: string;
  subtype: string | null;
  fields: {
    rechnungsnummer?: string | null;
    marktlokation?: string | null;
    customer_name?: string | null;
    amount_eur?: number | null;
    [k: string]: unknown;
  };
  warnings: string[];
  recipient?: Recipient;
}

export interface EmailGroup {
  matched: boolean;
  unternehmen: string | null;
  to: string[];
  cc: string[];
  malos: string[];
  documents: string[];
  doc_ids: string[];
  warnings: string[];
}

export interface OrphanRecipient {
  unternehmen: string | null;
  kundennummer: string | null;
  malos: string[];
  to: string[];
  cc: string[];
}

export interface ProcessResponse {
  batch_id: string;
  total: number;
  summary: {
    categories: Record<string, number>;
    invoice_subtypes: Record<string, number>;
    needs_review: number;
    emails_to_send: number;
    unmatched_documents: number;
    recipients_without_pdf: number;
    mapping_entries: number;
  };
  emails: EmailGroup[];
  documents: DocResult[];
  orphan_recipients: OrphanRecipient[];
}

export type StepId = 'upload' | 'validation' | 'portal' | 'send';

export interface DraftAttachment {
  doc_id: string;
  filename: string;
  category: string;
  subtype: string | null;
}

export interface EmailDraft {
  draft_id: string;
  batch_id: string;
  category: string;
  unternehmen: string | null;
  to: string[];
  cc: string[];
  subject: string;
  html: string;
  attachments: DraftAttachment[];
  status: 'READY' | 'BLOCKED' | 'SENT' | 'FAILED';
  warnings: string[];
  error: string | null;
}

export interface SendResultItem {
  draft_id: string;
  sent: boolean;
  status: string;
  detail: string | null;
}

export interface SendMode {
  app_env: string;
  backend: string;
  sandbox: boolean;
  delivers: boolean;
  label: string;
  real_send_blocked: boolean;
}
