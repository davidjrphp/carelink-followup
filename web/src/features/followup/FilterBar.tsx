import type { Facility, SortOrder } from '../../api/types';
import { Icon } from '../../components/Icon';
import { MAX_THRESHOLD, SORT_OPTIONS, STATUS_FILTERS, type StatusFilter } from './filters';

interface Props {
  facilities: Facility[];
  facilityId: string | null;
  facilityLocked: boolean;
  onFacilityChange: (id: string) => void;
  status: StatusFilter;
  onStatusChange: (s: StatusFilter) => void;
  thresholdInput: string;
  thresholdError: string | null;
  onThresholdChange: (raw: string) => void;
  search: string;
  onSearchChange: (s: string) => void;
  sort: SortOrder;
  onSortChange: (s: SortOrder) => void;
  canReset: boolean;
  onReset: () => void;
}

export function FilterBar(p: Props) {
  const lockedFacility = p.facilities.find((f) => f.facility_id === p.facilityId);
  return (
    <form className="filters" role="search" aria-label="Filter the follow-up list"
      onSubmit={(e) => e.preventDefault()}>
      <div className="field field--facility">
        {p.facilityLocked ? (
          <>
            <span className="field__label" id="f-facility-label">Facility</span>
            <p className="field__static" aria-labelledby="f-facility-label">
              <Icon name="building" size={16} />
              <span className="field__static-text">{lockedFacility?.name ?? p.facilityId}</span>
              <span className="field__static-id">{p.facilityId}</span>
            </p>
          </>
        ) : (
          <>
          <label htmlFor="f-facility">Facility</label>
          <select id="f-facility" value={p.facilityId ?? ''} onChange={(e) => p.onFacilityChange(e.target.value)}>
            {groupByDistrict(p.facilities).map(([district, list]) => (
              <optgroup key={district} label={`${district} district`}>
                {list.map((f) => (
                  <option key={f.facility_id} value={f.facility_id}>{f.name}</option>
                ))}
              </optgroup>
            ))}
          </select>
          </>
        )}
      </div>

      <div className="field">
        <label htmlFor="f-status">Status</label>
        <select id="f-status" value={p.status} onChange={(e) => p.onStatusChange(e.target.value as StatusFilter)}>
          {STATUS_FILTERS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      <div className="field field--narrow">
        <label htmlFor="f-threshold">Missed by more than</label>
        <div className="input-suffix">
          <input
            id="f-threshold"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={p.thresholdInput}
            onChange={(e) => p.onThresholdChange(e.target.value)}
            aria-invalid={p.thresholdError ? true : undefined}
            aria-describedby={p.thresholdError ? 'f-threshold-hint f-threshold-error' : 'f-threshold-hint'}
          />
          <span aria-hidden="true">days</span>
        </div>
        <p id="f-threshold-hint" className="field__hint">0 to {MAX_THRESHOLD} days</p>
        {p.thresholdError && (
          <p id="f-threshold-error" className="field__error" role="alert">
            <Icon name="alert" size={14} />{p.thresholdError}
          </p>
        )}
      </div>

      <div className="field field--grow">
        <label htmlFor="f-search">Search</label>
        <div className="input-icon">
          <Icon name="search" />
          <input
            id="f-search"
            type="search"
            autoComplete="off"
            spellCheck={false}
            placeholder="Last name, first name or patient number"
            value={p.search}
            onChange={(e) => p.onSearchChange(e.target.value)}
            aria-describedby="f-search-hint"
            maxLength={100}
          />
        </div>
        <p id="f-search-hint" className="field__hint">Matches the start of a name or number</p>
      </div>

      <div className="field">
        <label htmlFor="f-sort">Sort by</label>
        <select id="f-sort" value={p.sort} onChange={(e) => p.onSortChange(e.target.value as SortOrder)}>
          {SORT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      <div className="field field--actions">
        <button type="button" className="btn btn--ghost" onClick={p.onReset} disabled={!p.canReset}>
          Reset filters
        </button>
      </div>
    </form>
  );
}

function groupByDistrict(facilities: Facility[]): [string, Facility[]][] {
  const groups = new Map<string, Facility[]>();
  for (const f of facilities) groups.set(f.district, [...(groups.get(f.district) ?? []), f]);
  return [...groups.entries()];
}
