/**
 * Measurement harness for the 10,000-row requirement (README, "Performance evidence").
 * Renders the real FollowUpTable with 10,000 invented rows, either virtualised (what ships) or with
 * every row in the DOM (the "before"), and records time-to-first-paint and DOM size on window.__bench.
 *   /bench.html?mode=virtual   /bench.html?mode=naive
 */
import { createRoot } from 'react-dom/client';
import type { FollowUpItem, FollowUpStatus } from '../api/types';
import { FollowUpTable } from '../features/followup/FollowUpTable';
import '../styles/app.css';

declare global {
  interface Window { __bench?: { mode: string; rows: number; renderMs: number; domNodes: number } }
}

const ROWS = 10_000;
const NAMES = ['Banda', 'Phiri', 'Zulu', 'Mwale', 'Tembo', 'Mumba', 'Lungu', 'Daka'];
const STATUSES: FollowUpStatus[] = ['overdue', 'missed'];

function fixture(n: number): FollowUpItem[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `p_${i}`,
    patient_number: `0101-${String(i).padStart(6, '0')}`,
    first_name: 'Test',
    last_name: NAMES[i % NAMES.length],
    facility_id: 'FAC-0101',
    facility_name: 'Mwansa Urban Clinic',
    missed_appointment_date: '2026-09-05',
    days_overdue: 400 - Math.floor(i / 25),
    follow_up_status: STATUSES[i % 2],
    phone_number: i % 5 === 0 ? null : `+26097${String(i).padStart(7, '0')}`,
    last_contact_attempt: i % 3 === 0 ? '2026-09-29T09:14:00Z' : null,
    last_visit_date: '2026-08-05',
  }));
}

const mode = new URLSearchParams(location.search).get('mode') === 'naive' ? 'naive' : 'virtual';
const items = fixture(ROWS);
const start = performance.now();

createRoot(document.getElementById('root') as HTMLElement).render(
  <main className="main">
    <section className="results">
      <FollowUpTable
        items={items}
        total={ROWS}
        sort="days_overdue_desc"
        onSortChange={() => undefined}
        canWrite
        onRecordContact={() => undefined}
        virtualize={mode === 'virtual'}
      />
    </section>
  </main>,
);

// Two animation frames after commit = the browser has laid out and painted the first frame.
requestAnimationFrame(() => requestAnimationFrame(() => {
  window.__bench = {
    mode,
    rows: ROWS,
    renderMs: Math.round(performance.now() - start),
    domNodes: document.querySelectorAll('*').length,
  };
}));
