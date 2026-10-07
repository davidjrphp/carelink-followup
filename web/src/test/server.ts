import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import type { Facility, FollowUpItem, FollowUpPage, FollowUpSummary, Me } from '../api/types';

export const CLINICIAN: Me = { user_id: 'clinician.fac0101', role: 'CLINICIAN', facility_id: 'FAC-0101', can_write: true };
export const DISTRICT: Me = { user_id: 'district.officer', role: 'DISTRICT_OFFICER', facility_id: null, can_write: false };

export const FACILITIES: Facility[] = [
  { facility_id: 'FAC-0101', name: 'Mwansa Urban Clinic', district: 'Mwansa' },
  { facility_id: 'FAC-0207', name: 'Kalemba Rural Health Centre', district: 'Kalemba' },
];

// The pack's sample response (section 15.3), with ids as our API returns them.
export const ITEMS: FollowUpItem[] = [
  {
    id: '11111111-1111-4111-8111-111111111111', patient_number: '0101-000471', first_name: 'Thandiwe',
    last_name: 'Banda', facility_id: 'FAC-0101', facility_name: 'Mwansa Urban Clinic',
    missed_appointment_date: '2026-09-05', days_overdue: 31, follow_up_status: 'overdue',
    phone_number: '+260970000471', last_contact_attempt: null, last_visit_date: '2026-08-05',
  },
  {
    id: '22222222-2222-4222-8222-222222222222', patient_number: '0101-000472', first_name: 'Mulenga',
    last_name: 'Phiri', facility_id: 'FAC-0101', facility_name: 'Mwansa Urban Clinic',
    missed_appointment_date: '2026-09-10', days_overdue: 26, follow_up_status: 'overdue',
    phone_number: null, last_contact_attempt: '2026-09-29T09:14:00Z', last_visit_date: '2026-08-20',
  },
  {
    id: '33333333-3333-4333-8333-333333333333', patient_number: '0101-000088', first_name: 'Chanda',
    last_name: 'Mwale', facility_id: 'FAC-0101', facility_name: 'Mwansa Urban Clinic',
    missed_appointment_date: '2026-09-28', days_overdue: 8, follow_up_status: 'missed',
    phone_number: '+260971000088', last_contact_attempt: null, last_visit_date: '2026-08-28',
  },
];

export function page(items: FollowUpItem[], overrides: Partial<FollowUpPage> = {}): FollowUpPage {
  return { page: 1, page_size: 100, total: items.length, as_of: '2026-10-06', overdue_days: 7, items, ...overrides };
}

export const SUMMARY: FollowUpSummary = {
  facility_id: 'FAC-0101', as_of: '2026-10-06', overdue_days: 7, counts: { overdue: 2, missed: 1, due_soon: 4 },
};

export const handlers = [
  http.get('*/api/me', () => HttpResponse.json(CLINICIAN)),
  http.get('*/api/facilities', () => HttpResponse.json([FACILITIES[0]])),
  http.get('*/api/follow-up/summary', () => HttpResponse.json(SUMMARY)),
  http.get('*/api/follow-up', () => HttpResponse.json(page(ITEMS))),
  http.post('*/api/follow-up/:id/contacted', () => new HttpResponse(null, { status: 204 })),
];

export const server = setupServer(...handlers);
