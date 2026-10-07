// Typed mirror of the API contract (pack section 15.2 plus the additive fields documented in the README).

export type FollowUpStatus = 'due_soon' | 'missed' | 'overdue';
export type SortOrder = 'days_overdue_desc' | 'days_overdue_asc' | 'name_asc';
export type Role = 'CLINICIAN' | 'DISTRICT_OFFICER';

export interface FollowUpItem {
  id: string;
  patient_number: string;
  first_name: string;
  last_name: string;
  facility_id: string;
  facility_name: string;
  missed_appointment_date: string; // ISO date
  /** Negative for due_soon: -3 means the appointment is in 3 days. */
  days_overdue: number;
  follow_up_status: FollowUpStatus;
  phone_number: string | null;
  last_contact_attempt: string | null; // ISO timestamp
  last_visit_date: string; // ISO date
}

export interface FollowUpPage {
  page: number;
  page_size: number;
  total: number;
  as_of: string;
  overdue_days: number;
  items: FollowUpItem[];
}

export interface FollowUpSummary {
  facility_id: string;
  as_of: string;
  overdue_days: number;
  counts: Record<FollowUpStatus, number>;
}

export interface Facility {
  facility_id: string;
  name: string;
  district: string;
}

export interface Me {
  user_id: string;
  role: Role;
  facility_id: string | null;
  can_write: boolean;
}

export interface FieldError {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    correlation_id: string;
    details?: FieldError[];
  };
}

export interface FollowUpQuery {
  facilityId: string;
  statuses: FollowUpStatus[];
  overdueDays: number;
  sort: SortOrder;
  search: string;
}

export interface ContactAttemptInput {
  contacted_at: string; // ISO timestamp with offset
  note: string | null;
}
