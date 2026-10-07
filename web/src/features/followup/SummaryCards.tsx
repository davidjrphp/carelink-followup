import type { FollowUpSummary } from '../../api/types';
import { Icon, type IconName } from '../../components/Icon';
import { formatCount } from '../../lib/format';
import type { StatusFilter } from './filters';

interface Card {
  filter: StatusFilter;
  label: string;
  hint: string;
  icon: IconName;
  count: (s: FollowUpSummary) => number;
}

const CARDS: Card[] = [
  { filter: 'needs_follow_up', label: 'Needs follow-up', hint: 'Missed and overdue', icon: 'users',
    count: (s) => s.counts.missed + s.counts.overdue },
  { filter: 'overdue', label: 'Overdue', hint: 'More than 14 days past', icon: 'alert',
    count: (s) => s.counts.overdue },
  { filter: 'missed', label: 'Recently missed', hint: 'Within 14 days', icon: 'clock',
    count: (s) => s.counts.missed },
  { filter: 'due_soon', label: 'Due soon', hint: 'Next 7 days', icon: 'calendar',
    count: (s) => s.counts.due_soon },
];

interface Props {
  summary: FollowUpSummary | undefined;
  failed: boolean;
  active: StatusFilter;
  onSelect: (filter: StatusFilter) => void;
}

/** Counts double as quick filters: real toggle buttons with aria-pressed. */
export function SummaryCards({ summary, failed, active, onSelect }: Props) {
  return (
    <ul className="summary" aria-label="Follow-up counts. Select one to filter the list.">
      {CARDS.map((card) => (
        <li key={card.filter}>
          <button
            type="button"
            className={`summary-card summary-card--${card.filter}`}
            aria-pressed={active === card.filter}
            onClick={() => onSelect(card.filter)}
          >
            <span className="summary-card__icon"><Icon name={card.icon} size={18} /></span>
            <span className="summary-card__body">
              <span className="summary-card__label">{card.label}</span>
              <span className="summary-card__count">
                {summary ? formatCount(card.count(summary)) : failed ? '–' : <span className="skeleton__bar skeleton__bar--count" aria-label="Loading" />}
              </span>
              <span className="summary-card__hint">{card.hint}</span>
            </span>
            {active === card.filter && (
              <span className="summary-card__check"><Icon name="check" size={14} /><span className="sr-only">(showing)</span></span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
