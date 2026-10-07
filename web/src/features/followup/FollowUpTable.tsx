import { useVirtualizer } from '@tanstack/react-virtual';
import { memo, useEffect, useRef } from 'react';
import type { FollowUpItem, SortOrder } from '../../api/types';
import { Icon } from '../../components/Icon';
import { StatusBadge } from '../../components/StatusBadge';
import { describeDays, formatCount, formatDate, formatDateTime } from '../../lib/format';

export const ROW_HEIGHT = 64;
const LOAD_AHEAD_ROWS = 30;

export interface FollowUpTableProps {
  items: FollowUpItem[];
  total: number;
  sort: SortOrder;
  onSortChange: (sort: SortOrder) => void;
  canWrite: boolean;
  onRecordContact: (item: FollowUpItem, trigger: HTMLButtonElement) => void;
  hasNextPage?: boolean;
  isFetchingNextPage?: boolean;
  nextPageFailed?: boolean;
  onLoadMore?: () => void;
  /** false renders every row: used only by the benchmark to measure the "before" case. */
  virtualize?: boolean;
}

type AriaSort = 'ascending' | 'descending' | 'none';

export function FollowUpTable({
  items, total, sort, onSortChange, canWrite, onRecordContact,
  hasNextPage = false, isFetchingNextPage = false, nextPageFailed = false, onLoadMore,
  virtualize = true,
}: FollowUpTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: virtualize ? items.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const lastVisible = virtualize ? virtualRows[virtualRows.length - 1]?.index ?? -1 : items.length - 1;

  // Fetch the next server page shortly before the user scrolls to the end of what is loaded.
  useEffect(() => {
    if (lastVisible >= items.length - LOAD_AHEAD_ROWS && hasNextPage && !isFetchingNextPage && !nextPageFailed) {
      onLoadMore?.();
    }
  }, [lastVisible, items.length, hasNextPage, isFetchingNextPage, nextPageFailed, onLoadMore]);

  const rows = virtualize
    ? virtualRows.map((v) => ({ item: items[v.index], index: v.index }))
    : items.map((item, index) => ({ item, index }));
  const paddingTop = virtualize ? virtualRows[0]?.start ?? 0 : 0;
  const paddingBottom = virtualize
    ? virtualizer.getTotalSize() - (virtualRows[virtualRows.length - 1]?.end ?? 0)
    : 0;
  const columns = canWrite ? 7 : 6;

  const daysSort: AriaSort =
    sort === 'days_overdue_desc' ? 'descending' : sort === 'days_overdue_asc' ? 'ascending' : 'none';
  const nameSort: AriaSort = sort === 'name_asc' ? 'ascending' : 'none';

  return (
    <div
      ref={scrollRef}
      className="table-scroll"
      // Focusable so keyboard users can scroll the region with the arrow keys.
      tabIndex={0}
      role="region"
      aria-label="Follow-up list, scrollable"
    >
      <table className="fu-table" aria-rowcount={total + 1}>
        <caption className="sr-only">
          Patients needing follow-up. {formatCount(total)} in total; more rows load as you scroll.
        </caption>
        <colgroup>
          <col className="col-patient" />
          <col className="col-phone" />
          <col className="col-appt" />
          <col className="col-days" />
          <col className="col-status" />
          <col className="col-contact" />
          {canWrite && <col className="col-action" />}
        </colgroup>
        <thead>
          <tr aria-rowindex={1}>
            <th scope="col" aria-sort={nameSort}>
              <button type="button" className="th-sort" onClick={() => onSortChange('name_asc')}>
                Patient
                <Icon name={nameSort === 'ascending' ? 'arrowDown' : 'sort'} size={14}
                  className={nameSort === 'none' ? 'th-sort__idle' : undefined} />
                <span className="sr-only">{nameSort === 'none' ? ', sort by name' : ', sorted A to Z'}</span>
              </button>
            </th>
            <th scope="col">Phone</th>
            <th scope="col">Appointment</th>
            <th scope="col" aria-sort={daysSort} className="num">
              <button
                type="button"
                className="th-sort th-sort--num"
                onClick={() => onSortChange(sort === 'days_overdue_desc' ? 'days_overdue_asc' : 'days_overdue_desc')}
              >
                Days overdue
                <Icon name={daysSort === 'ascending' ? 'arrowUp' : daysSort === 'descending' ? 'arrowDown' : 'sort'}
                  size={14} className={daysSort === 'none' ? 'th-sort__idle' : undefined} />
                <span className="sr-only">
                  {daysSort === 'descending' ? ', most overdue first' : daysSort === 'ascending'
                    ? ', least overdue first' : ', sort by days overdue'}
                </span>
              </button>
            </th>
            <th scope="col">Status</th>
            <th scope="col">Last contact</th>
            {canWrite && <th scope="col"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 && (
            <tr aria-hidden="true" className="spacer"><td colSpan={columns} style={{ height: paddingTop }} /></tr>
          )}
          {rows.map(({ item, index }) => (
            <Row key={item.id} item={item} rowIndex={index + 2} canWrite={canWrite} onRecordContact={onRecordContact} />
          ))}
          {paddingBottom > 0 && (
            <tr aria-hidden="true" className="spacer"><td colSpan={columns} style={{ height: paddingBottom }} /></tr>
          )}
        </tbody>
      </table>
      <div className="table-footer">
        {isFetchingNextPage && <span className="table-footer__loading"><span className="spinner" aria-hidden="true" />Loading more patients…</span>}
        {nextPageFailed && (
          <span className="table-footer__error" role="alert">
            Couldn&apos;t load more patients.
            <button type="button" className="btn btn--link" onClick={onLoadMore}>Try again</button>
          </span>
        )}
        {!hasNextPage && !isFetchingNextPage && items.length > 0 && (
          <span>End of list · {formatCount(items.length)} of {formatCount(total)} shown</span>
        )}
      </div>
    </div>
  );
}

interface RowProps {
  item: FollowUpItem;
  rowIndex: number;
  canWrite: boolean;
  onRecordContact: (item: FollowUpItem, trigger: HTMLButtonElement) => void;
}

const Row = memo(function Row({ item, rowIndex, canWrite, onRecordContact }: RowProps) {
  const name = `${item.first_name} ${item.last_name}`;
  return (
    <tr aria-rowindex={rowIndex} className={`fu-row fu-row--${item.follow_up_status}`}>
      <th scope="row" className="cell-patient">
        <span className="patient-name">{name}</span>
        <span className="patient-number">{item.patient_number}</span>
      </th>
      <td>
        {item.phone_number
          ? <span className="phone">{item.phone_number}</span>
          : <span className="muted">Not recorded</span>}
      </td>
      <td>
        <span className="cell-main">{formatDate(item.missed_appointment_date)}</span>
        <span className="cell-sub">Last visit {formatDate(item.last_visit_date)}</span>
      </td>
      <td className="num">
        <span className={`days days--${item.follow_up_status}`}>{describeDays(item.days_overdue)}</span>
      </td>
      <td><StatusBadge status={item.follow_up_status} /></td>
      <td>
        {item.last_contact_attempt
          ? <span className="cell-main">{formatDateTime(item.last_contact_attempt)}</span>
          : <span className="muted">No attempts yet</span>}
      </td>
      {canWrite && (
        <td className="cell-action">
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            aria-label={`Record contact with ${name}`}
            onClick={(e) => onRecordContact(item, e.currentTarget)}
          >
            <Icon name="phone" size={14} />
            Record contact
          </button>
        </td>
      )}
    </tr>
  );
});
