import type { ReactNode } from 'react';
import { ApiError } from '../api/http';
import { Icon, type IconName } from './Icon';

export function LoadingRows({ rows = 8 }: { rows?: number }) {
  return (
    <div className="skeleton" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton__row" key={i}>
          <span className="skeleton__bar skeleton__bar--wide" />
          <span className="skeleton__bar" />
          <span className="skeleton__bar" />
          <span className="skeleton__bar skeleton__bar--short" />
          <span className="skeleton__bar" />
        </div>
      ))}
    </div>
  );
}

function Panel({ icon, tone, title, children }: {
  icon: IconName; tone: 'neutral' | 'danger'; title: string; children?: ReactNode;
}) {
  return (
    <div className={`state-panel state-panel--${tone}`}>
      <span className="state-panel__icon"><Icon name={icon} size={24} /></span>
      <h2 className="state-panel__title">{title}</h2>
      {children}
    </div>
  );
}

export function EmptyState({ filtered, onReset }: { filtered: boolean; onReset: () => void }) {
  return (
    <Panel icon="inbox" tone="neutral" title="No patients need follow-up">
      <p className="state-panel__text">
        {filtered
          ? 'Nobody matches these filters. Try a different status, threshold or search.'
          : 'Every patient with a booked appointment has attended or is not yet due.'}
      </p>
      {filtered && (
        <button type="button" className="btn btn--secondary" onClick={onReset}>Clear filters</button>
      )}
    </Panel>
  );
}

export function ErrorState({ error, onRetry, retrying }: {
  error: unknown; onRetry: () => void; retrying: boolean;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const offline = apiError?.unreachable ?? false;
  return (
    <div role="alert">
      <Panel icon={offline ? 'wifiOff' : 'alert'} tone="danger"
        title={offline ? 'The follow-up list could not be loaded' : 'Something went wrong'}>
        <p className="state-panel__text">
          {apiError?.message ?? 'An unexpected error occurred.'}
        </p>
        {apiError?.correlationId && (
          <p className="state-panel__ref">Reference: <code>{apiError.correlationId}</code></p>
        )}
        <button type="button" className="btn btn--primary" onClick={onRetry} disabled={retrying}>
          <Icon name="refresh" />
          {retrying ? 'Retrying…' : 'Try again'}
        </button>
      </Panel>
    </div>
  );
}
