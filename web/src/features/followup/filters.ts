import type { FollowUpStatus, SortOrder } from '../../api/types';

export type StatusFilter = 'needs_follow_up' | 'overdue' | 'missed' | 'due_soon' | 'all';

export const STATUS_FILTERS: { value: StatusFilter; label: string; statuses: FollowUpStatus[] }[] = [
  { value: 'needs_follow_up', label: 'Missed and overdue', statuses: ['missed', 'overdue'] },
  { value: 'overdue', label: 'Overdue', statuses: ['overdue'] },
  { value: 'missed', label: 'Recently missed', statuses: ['missed'] },
  { value: 'due_soon', label: 'Due soon (7 days)', statuses: ['due_soon'] },
  { value: 'all', label: 'All statuses', statuses: ['overdue', 'missed', 'due_soon'] },
];

export const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
  { value: 'days_overdue_desc', label: 'Most overdue first' },
  { value: 'days_overdue_asc', label: 'Least overdue first' },
  { value: 'name_asc', label: 'Last name, A to Z' },
];

export const DEFAULT_THRESHOLD = 7;
export const MAX_THRESHOLD = 365;

export function statusesFor(filter: StatusFilter): FollowUpStatus[] {
  return STATUS_FILTERS.find((f) => f.value === filter)?.statuses ?? ['missed', 'overdue'];
}

/** Returns the parsed threshold, or an error message written for the person typing it. */
export function parseThreshold(raw: string): { value: number } | { error: string } {
  const trimmed = raw.trim();
  if (trimmed === '') return { error: 'Enter a number of days, for example 7.' };
  if (!/^\d+$/.test(trimmed)) return { error: 'Use whole days only, with no letters or decimals.' };
  const value = Number(trimmed);
  if (value > MAX_THRESHOLD) return { error: `Enter ${MAX_THRESHOLD} days or fewer.` };
  return { value };
}
