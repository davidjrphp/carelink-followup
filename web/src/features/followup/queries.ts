import {
  keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query';
import { followUpService } from '../../api/followUpService';
import type { ApiError } from '../../api/http';
import type { ContactAttemptInput, FollowUpPage, FollowUpQuery } from '../../api/types';

export const queryKeys = {
  me: ['me'] as const,
  facilities: ['facilities'] as const,
  list: (q: FollowUpQuery) => ['follow-up', 'list', q] as const,
  summary: (facilityId: string, overdueDays: number) =>
    ['follow-up', 'summary', facilityId, overdueDays] as const,
};

export function useMe(enabled = true) {
  return useQuery({ queryKey: queryKeys.me, queryFn: ({ signal }) => followUpService.getMe(signal),
    enabled, staleTime: Infinity });
}

export function useFacilities(enabled = true) {
  return useQuery({ queryKey: queryKeys.facilities,
    queryFn: ({ signal }) => followUpService.getFacilities(signal), enabled, staleTime: Infinity });
}

/**
 * Server-side paging, loaded on demand as the user scrolls. The AbortSignal cancels a superseded
 * request, and the query key includes every filter, so a late response for an old facility or
 * filter can never overwrite the current list.
 */
export function useFollowUpList(query: FollowUpQuery | null) {
  return useInfiniteQuery({
    queryKey: query ? queryKeys.list(query) : ['follow-up', 'list', 'disabled'],
    queryFn: ({ pageParam, signal }) => followUpService.getPage(query as FollowUpQuery, pageParam, signal),
    initialPageParam: 1,
    getNextPageParam: (last: FollowUpPage) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
    enabled: query !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useSummary(facilityId: string | null, overdueDays: number | null) {
  return useQuery({
    queryKey: queryKeys.summary(facilityId ?? '', overdueDays ?? 0),
    queryFn: ({ signal }) => followUpService.getSummary(facilityId as string, overdueDays as number, signal),
    enabled: facilityId !== null && overdueDays !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

interface RecordContactVars {
  patientId: string;
  input: ContactAttemptInput;
  idempotencyKey: string;
}

export function useRecordContact() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, RecordContactVars>({
    mutationFn: ({ patientId, input, idempotencyKey }) =>
      followUpService.recordContact(patientId, input, idempotencyKey),
    // Retry policy: QueryClient defaults (App.tsx). Safe because the same Idempotency-Key
    // goes with every attempt.
    onSuccess: (_data, { patientId, input }) => {
      // Patch the row in every cached page rather than refetching thousands of loaded rows.
      queryClient.setQueriesData<InfiniteData<FollowUpPage>>({ queryKey: ['follow-up', 'list'] }, (data) => {
        if (!data) return data;
        return {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.map((item) =>
              item.id === patientId &&
              (!item.last_contact_attempt || item.last_contact_attempt < input.contacted_at)
                ? { ...item, last_contact_attempt: input.contacted_at }
                : item),
          })),
        };
      });
    },
  });
}
