import { request } from './http';
import type {
  ContactAttemptInput, Facility, FollowUpPage, FollowUpQuery, FollowUpSummary, Me,
} from './types';

export const PAGE_SIZE = 100;

export const followUpService = {
  getPage(query: FollowUpQuery, page: number, signal?: AbortSignal): Promise<FollowUpPage> {
    return request<FollowUpPage>('/api/follow-up', {
      query: {
        facility_id: query.facilityId,
        status: query.statuses.join(','),
        overdue_days: query.overdueDays,
        sort: query.sort,
        q: query.search.trim(),
        page,
        page_size: PAGE_SIZE,
      },
      signal,
    });
  },

  getSummary(facilityId: string, overdueDays: number, signal?: AbortSignal): Promise<FollowUpSummary> {
    return request<FollowUpSummary>('/api/follow-up/summary', {
      query: { facility_id: facilityId, overdue_days: overdueDays },
      signal,
    });
  },

  /** The idempotency key is chosen once per user action and reused on every retry (Section D1). */
  recordContact(patientId: string, input: ContactAttemptInput, idempotencyKey: string): Promise<void> {
    return request<void>(`/api/follow-up/${encodeURIComponent(patientId)}/contacted`, {
      method: 'POST',
      body: input,
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  },

  getFacilities(signal?: AbortSignal): Promise<Facility[]> {
    return request<Facility[]>('/api/facilities', { signal });
  },

  getMe(signal?: AbortSignal, token?: string): Promise<Me> {
    return request<Me>('/api/me', { signal, token });
  },
};

export type FollowUpService = typeof followUpService;
