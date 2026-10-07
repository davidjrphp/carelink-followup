/**
 * Screen tests through the real component tree, service layer and HTTP client, with the network
 * mocked by MSW. They cover what would hurt a clinic most if it broke: the list silently failing,
 * status unreadable without colour, keyboard users locked out, and contact attempts lost or doubled.
 */
import { QueryClient } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { App } from '../../App';
import { DISTRICT, FACILITIES, ITEMS, page, server } from '../../test/server';

function renderApp(token = 'clin-0101-demo-token') {
  sessionStorage.setItem('carelink.session', token);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const user = userEvent.setup();
  return { user, ...render(<App queryClient={client} />) };
}

async function findTable() {
  return screen.findByRole('table');
}

function rowFor(name: string): HTMLElement {
  const header = screen.getByRole('rowheader', { name: new RegExp(name) });
  return header.closest('tr') as HTMLElement;
}

describe('follow-up list', () => {
  it('announces loading, then shows patients with status as text', async () => {
    renderApp();
    expect(await screen.findByText('Loading follow-up list…')).toBeInTheDocument();

    await findTable();
    const row = rowFor('Thandiwe Banda');
    expect(within(row).getByText('Overdue')).toBeInTheDocument(); // text, not just colour
    expect(within(row).getByText('31 days')).toBeInTheDocument();
    expect(within(row).getByText('0101-000471')).toBeInTheDocument();
    expect(within(rowFor('Chanda Mwale')).getByText('Missed')).toBeInTheDocument();
    expect(within(rowFor('Mulenga Phiri')).getByText('Not recorded')).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: '3 patients' })).toBeInTheDocument();
    expect(screen.getByText('3 patients found.')).toBeInTheDocument(); // aria-live region
  });

  it('sends the contract parameters: facility_id, status, overdue_days, sort, paging', async () => {
    const seen: URLSearchParams[] = [];
    server.use(http.get('*/api/follow-up', ({ request }) => {
      seen.push(new URL(request.url).searchParams);
      return HttpResponse.json(page(ITEMS));
    }));
    renderApp();
    await findTable();
    expect(Object.fromEntries(seen[0])).toEqual({
      facility_id: 'FAC-0101', status: 'missed,overdue', overdue_days: '7',
      sort: 'days_overdue_desc', page: '1', page_size: '100',
    });
  });

  it('shows an empty state that is distinct from an error', async () => {
    server.use(http.get('*/api/follow-up', () => HttpResponse.json(page([]))));
    renderApp();
    expect(await screen.findByRole('heading', { name: 'No patients need follow-up' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows an error with a retry path when the API is down, and recovers', async () => {
    let fail = true;
    server.use(http.get('*/api/follow-up', () => (fail ? HttpResponse.error() : HttpResponse.json(page(ITEMS)))));
    const { user } = renderApp();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Can't reach the CareLink server");
    expect(within(alert).getByText(/Reference:/)).toBeInTheDocument();

    fail = false;
    await user.click(within(alert).getByRole('button', { name: /try again/i }));
    expect(await findTable()).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the server error message and correlation id for a 500', async () => {
    server.use(http.get('*/api/follow-up', () => HttpResponse.json(
      { error: { code: 'INTERNAL_ERROR', message: 'Something went wrong on the server.', correlation_id: '8c21-44f1' } },
      { status: 500 })));
    renderApp();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Something went wrong on the server.');
    expect(alert).toHaveTextContent('8c21-44f1');
  });

  it('validates the threshold, associates the error with the field and keeps the last valid query', async () => {
    const thresholds: string[] = [];
    server.use(http.get('*/api/follow-up', ({ request }) => {
      thresholds.push(new URL(request.url).searchParams.get('overdue_days') ?? '');
      return HttpResponse.json(page(ITEMS));
    }));
    const { user } = renderApp();
    await findTable();

    const input = screen.getByLabelText('Missed by more than');
    await user.clear(input);
    await user.type(input, '7x');

    const error = await screen.findByText('Use whole days only, with no letters or decimals.');
    expect(error.closest('[role="alert"]')).not.toBeNull();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/Use whole days only/);
    await act(() => new Promise((r) => setTimeout(r, 500))); // let the debounce elapse
    expect(thresholds.every((t) => t === '7')).toBe(true);

    await user.clear(input);
    await user.type(input, '30');
    await waitFor(() => expect(thresholds).toContain('30'));
    expect(input).not.toHaveAttribute('aria-invalid');
  });

  it('sorts from the column header and exposes aria-sort', async () => {
    const sorts: string[] = [];
    server.use(http.get('*/api/follow-up', ({ request }) => {
      sorts.push(new URL(request.url).searchParams.get('sort') ?? '');
      return HttpResponse.json(page(ITEMS));
    }));
    const { user } = renderApp();
    await findTable();
    const header = screen.getByRole('columnheader', { name: /days overdue/i });
    expect(header).toHaveAttribute('aria-sort', 'descending');

    await user.click(within(header).getByRole('button'));
    await waitFor(() => expect(sorts).toContain('days_overdue_asc'));
    expect(screen.getByRole('columnheader', { name: /days overdue/i })).toHaveAttribute('aria-sort', 'ascending');
  });

  it('filters by status from the summary cards', async () => {
    const statuses: string[] = [];
    server.use(http.get('*/api/follow-up', ({ request }) => {
      statuses.push(new URL(request.url).searchParams.get('status') ?? '');
      return HttpResponse.json(page(ITEMS));
    }));
    const { user } = renderApp();
    await findTable();
    const dueSoon = screen.getByRole('button', { name: /due soon/i, pressed: false });
    await user.click(dueSoon);
    await waitFor(() => expect(statuses).toContain('due_soon'));
    expect(screen.getByRole('button', { name: /due soon/i, pressed: true })).toBeInTheDocument();
    expect(screen.getByLabelText('Status')).toHaveValue('due_soon');
  });
});

describe('recording a contact attempt', () => {
  it('works with the keyboard alone and sends the contract body with an Idempotency-Key', async () => {
    const posts: { body: unknown; key: string | null; id: string }[] = [];
    server.use(http.post('*/api/follow-up/:id/contacted', async ({ request, params }) => {
      posts.push({ body: await request.json(), key: request.headers.get('Idempotency-Key'), id: String(params.id) });
      return new HttpResponse(null, { status: 204 });
    }));
    const { user } = renderApp();
    await findTable();

    const button = within(rowFor('Thandiwe Banda')).getByRole('button', { name: 'Record contact with Thandiwe Banda' });
    button.focus();
    await user.keyboard('{Enter}');

    const dialog = await screen.findByRole('dialog', { name: 'Record contact attempt' });
    expect(within(dialog).getByLabelText('Date and time of contact attempt')).toHaveFocus();
    await user.tab();
    expect(within(dialog).getByLabelText(/Outcome/)).toHaveFocus();
    await user.keyboard('No answer, will try again');
    await user.tab(); // Cancel
    await user.tab(); // Save
    expect(within(dialog).getByRole('button', { name: /save contact attempt/i })).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(await screen.findByRole('status')).toHaveTextContent('Contact attempt recorded for Thandiwe Banda.');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(posts).toHaveLength(1);
    expect(posts[0].id).toBe(ITEMS[0].id);
    expect(posts[0].key).toMatch(/^[A-Za-z0-9-]{8,}$/);
    const body = posts[0].body as { contacted_at: string; note: string };
    expect(body.note).toBe('No answer, will try again');
    expect(body.contacted_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    // The row updates in place without refetching the list.
    expect(within(rowFor('Thandiwe Banda')).queryByText('No attempts yet')).not.toBeInTheDocument();
  });

  it('closes on Escape and returns focus to the button that opened it', async () => {
    const { user } = renderApp();
    await findTable();
    const button = within(rowFor('Chanda Mwale')).getByRole('button', { name: /record contact/i });
    await user.click(button);
    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(button).toHaveFocus());
  });

  it('says clearly when a save fails, and a retry reuses the same Idempotency-Key', async () => {
    const keys: (string | null)[] = [];
    let fail = true;
    server.use(http.post('*/api/follow-up/:id/contacted', ({ request }) => {
      keys.push(request.headers.get('Idempotency-Key'));
      return fail ? HttpResponse.error() : new HttpResponse(null, { status: 204 });
    }));
    const { user } = renderApp();
    await findTable();
    await user.click(within(rowFor('Thandiwe Banda')).getByRole('button', { name: /record contact/i }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /save contact attempt/i }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('Not saved');
    expect(alert).toHaveTextContent('it will not be recorded twice');

    fail = false;
    await user.click(within(dialog).getByRole('button', { name: /save contact attempt/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('rejects a contact time in the future and links the error to the field', async () => {
    const { user } = renderApp();
    await findTable();
    await user.click(within(rowFor('Thandiwe Banda')).getByRole('button', { name: /record contact/i }));
    const dialog = await screen.findByRole('dialog');
    const when = within(dialog).getByLabelText('Date and time of contact attempt');
    await user.clear(when);
    await user.type(when, '2099-01-01T10:00');
    await user.click(within(dialog).getByRole('button', { name: /save contact attempt/i }));

    expect(when).toHaveAttribute('aria-invalid', 'true');
    expect(when).toHaveAccessibleDescription('The contact time cannot be in the future.');
    expect(when).toHaveFocus();
  });
});

describe('district officer', () => {
  it('can choose a facility but has no write actions', async () => {
    server.use(
      http.get('*/api/me', () => HttpResponse.json(DISTRICT)),
      http.get('*/api/facilities', () => HttpResponse.json(FACILITIES)),
    );
    renderApp('district-demo-token');
    await findTable();
    expect(screen.getByLabelText('Facility')).toHaveValue('FAC-0101');
    expect(screen.queryByRole('button', { name: /record contact/i })).not.toBeInTheDocument();
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
  });
});
