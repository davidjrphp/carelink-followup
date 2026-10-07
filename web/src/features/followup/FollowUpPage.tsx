import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Facility, FollowUpItem, FollowUpQuery, Me, SortOrder } from '../../api/types';
import { EmptyState, ErrorState, LoadingRows } from '../../components/StateViews';
import { Toast } from '../../components/Toast';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import { formatCount, formatLongDate, plural } from '../../lib/format';
import { ContactDialog } from './ContactDialog';
import { FilterBar } from './FilterBar';
import { DEFAULT_THRESHOLD, parseThreshold, statusesFor, type StatusFilter } from './filters';
import { FollowUpTable } from './FollowUpTable';
import { useFollowUpList, useSummary } from './queries';
import { SummaryCards } from './SummaryCards';

interface Props {
  me: Me;
  facilities: Facility[];
}

const DEFAULT_STATUS: StatusFilter = 'needs_follow_up';
const DEFAULT_SORT: SortOrder = 'days_overdue_desc';

export function FollowUpPage({ me, facilities }: Props) {
  const facilityLocked = me.facility_id !== null;
  const [facilityId, setFacilityId] = useState<string | null>(
    me.facility_id ?? facilities[0]?.facility_id ?? null);
  const [status, setStatus] = useState<StatusFilter>(DEFAULT_STATUS);
  const [sort, setSort] = useState<SortOrder>(DEFAULT_SORT);
  const [thresholdInput, setThresholdInput] = useState(String(DEFAULT_THRESHOLD));
  const [search, setSearch] = useState('');
  const [dialogItem, setDialogItem] = useState<FollowUpItem | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  // The threshold is applied only when valid; the last valid value stays in effect meanwhile.
  const parsed = parseThreshold(thresholdInput);
  const thresholdError = 'error' in parsed ? parsed.error : null;
  const [overdueDays, setOverdueDays] = useState(DEFAULT_THRESHOLD);
  const debouncedThreshold = useDebouncedValue(thresholdInput, 400);
  useEffect(() => {
    const p = parseThreshold(debouncedThreshold);
    if ('value' in p) setOverdueDays(p.value);
  }, [debouncedThreshold]);
  const debouncedSearch = useDebouncedValue(search, 300);

  const query: FollowUpQuery | null = useMemo(() => facilityId === null ? null : ({
    facilityId, statuses: statusesFor(status), overdueDays, sort, search: debouncedSearch.trim(),
  }), [facilityId, status, overdueDays, sort, debouncedSearch]);

  const list = useFollowUpList(query);
  const summary = useSummary(facilityId, overdueDays);
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const firstPage = list.data?.pages[0];
  const total = firstPage?.total ?? 0;
  const facility = facilities.find((f) => f.facility_id === facilityId);
  const filtered = status !== DEFAULT_STATUS || debouncedSearch.trim() !== '' || overdueDays !== DEFAULT_THRESHOLD;
  const canReset = filtered || sort !== DEFAULT_SORT || thresholdInput !== String(DEFAULT_THRESHOLD) || search !== '';

  const resetFilters = useCallback(() => {
    setStatus(DEFAULT_STATUS);
    setSort(DEFAULT_SORT);
    setThresholdInput(String(DEFAULT_THRESHOLD));
    setOverdueDays(DEFAULT_THRESHOLD);
    setSearch('');
  }, []);

  const openDialog = useCallback((item: FollowUpItem, trigger: HTMLButtonElement) => {
    triggerRef.current = trigger;
    setDialogItem(item);
  }, []);

  const closeDialog = useCallback(() => {
    setDialogItem(null);
    // Return focus to the button that opened the dialog (if its row is still rendered).
    requestAnimationFrame(() => triggerRef.current?.isConnected && triggerRef.current.focus());
  }, []);

  const { fetchNextPage } = list;
  const loadMore = useCallback(() => { void fetchNextPage(); }, [fetchNextPage]);

  const showInitialLoading = list.isPending && query !== null;
  const showError = list.isError && items.length === 0;
  const nextPageFailed = list.isFetchNextPageError;

  // One polite announcement per result change, not per scroll-loaded page.
  const announcement = showInitialLoading
    ? 'Loading follow-up list…'
    : showError ? ''
      : firstPage ? `${plural(total, 'patient')} found.` : '';

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Follow-up list</h1>
          <p className="page-subtitle">
            Patients whose most recent visit booked an appointment they have not attended
            {facility ? <> · <strong>{facility.name}</strong></> : null}
          </p>
        </div>
        {firstPage && (
          <p className="as-of">
            <span className="as-of__label">As of</span> {formatLongDate(firstPage.as_of)}
          </p>
        )}
      </div>

      <SummaryCards summary={summary.data} failed={summary.isError} active={status} onSelect={setStatus} />

      <FilterBar
        facilities={facilities}
        facilityId={facilityId}
        facilityLocked={facilityLocked}
        onFacilityChange={setFacilityId}
        status={status}
        onStatusChange={setStatus}
        thresholdInput={thresholdInput}
        thresholdError={thresholdError}
        onThresholdChange={setThresholdInput}
        search={search}
        onSearchChange={setSearch}
        sort={sort}
        onSortChange={setSort}
        canReset={canReset}
        onReset={resetFilters}
      />

      <section className="results" aria-labelledby="results-heading" id="results">
        <div className="results__head">
          <h2 id="results-heading" className="results__title">
            {firstPage ? `${formatCount(total)} ${total === 1 ? 'patient' : 'patients'}` : 'Patients'}
          </h2>
          <p className="results__meta">
            {firstPage && <>Missed by more than {plural(firstPage.overdue_days, 'day')}</>}
            {list.isFetching && !list.isFetchingNextPage && !showInitialLoading && (
              <span className="results__refreshing"><span className="spinner" aria-hidden="true" />Updating…</span>
            )}
          </p>
        </div>

        <div className="results__body" aria-busy={showInitialLoading || undefined}>
          {showInitialLoading && <LoadingRows />}
          {showError && (
            <ErrorState error={list.error} onRetry={() => void list.refetch()} retrying={list.isFetching} />
          )}
          {!showInitialLoading && !showError && firstPage && items.length === 0 && (
            <EmptyState filtered={filtered} onReset={resetFilters} />
          )}
          {items.length > 0 && (
            <FollowUpTable
              items={items}
              total={total}
              sort={sort}
              onSortChange={setSort}
              canWrite={me.can_write}
              onRecordContact={openDialog}
              hasNextPage={list.hasNextPage}
              isFetchingNextPage={list.isFetchingNextPage}
              nextPageFailed={nextPageFailed}
              onLoadMore={loadMore}
            />
          )}
        </div>
      </section>

      <div className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</div>

      {dialogItem && (
        <ContactDialog
          item={dialogItem}
          onClose={closeDialog}
          onSaved={(saved) => {
            closeDialog();
            setToast(`Contact attempt recorded for ${saved.first_name} ${saved.last_name}.`);
          }}
        />
      )}
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </>
  );
}
