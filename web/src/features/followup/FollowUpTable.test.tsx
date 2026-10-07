import { render, screen } from '@testing-library/react';
import type { FollowUpItem } from '../../api/types';
import { ITEMS } from '../../test/server';
import { FollowUpTable } from './FollowUpTable';

function many(n: number): FollowUpItem[] {
  return Array.from({ length: n }, (_, i) => ({ ...ITEMS[i % 3], id: `p_${i}`, patient_number: `0101-${i}` }));
}

const noop = () => undefined;

describe('FollowUpTable with 10,000 rows', () => {
  it('keeps only a window of rows in the DOM, while announcing the full row count', () => {
    render(<FollowUpTable items={many(10_000)} total={10_000} sort="days_overdue_desc"
      onSortChange={noop} canWrite onRecordContact={noop} />);
    const bodyRows = screen.getAllByRole('row').filter((r) => r.hasAttribute('aria-rowindex') && r.getAttribute('aria-rowindex') !== '1');
    expect(bodyRows.length).toBeGreaterThan(5);
    expect(bodyRows.length).toBeLessThan(40);
    expect(screen.getByRole('table')).toHaveAttribute('aria-rowcount', '10001');
    expect(bodyRows[0]).toHaveAttribute('aria-rowindex', '2');
  });

  it('asks for the next page when the user nears the end of what is loaded', () => {
    const onLoadMore = vi.fn();
    render(<FollowUpTable items={many(20)} total={500} sort="days_overdue_desc" onSortChange={noop}
      canWrite onRecordContact={noop} hasNextPage onLoadMore={onLoadMore} />);
    expect(onLoadMore).toHaveBeenCalled();
  });

  it('offers a retry when loading more fails', () => {
    render(<FollowUpTable items={many(20)} total={500} sort="days_overdue_desc" onSortChange={noop}
      canWrite onRecordContact={noop} hasNextPage nextPageFailed onLoadMore={noop} />);
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't load more patients.");
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
