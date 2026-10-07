import type { ReactNode } from 'react';
import type { Facility, Me } from '../api/types';
import { Icon, LogoMark } from './Icon';

const ROLE_LABEL: Record<Me['role'], string> = {
  CLINICIAN: 'Clinician',
  DISTRICT_OFFICER: 'District officer',
};

interface Props {
  me: Me | null;
  facility: Facility | undefined;
  onSignOut: () => void;
  children: ReactNode;
}

export function AppShell({ me, facility, onSignOut, children }: Props) {
  return (
    <div className="app">
      <a className="skip-link" href="#results">Skip to results</a>
      <header className="topbar">
        <div className="topbar__inner">
          <div className="brand">
            <LogoMark />
            <span className="brand__name">CareLink</span>
            <span className="brand__divider" aria-hidden="true" />
            <span className="brand__module">Follow-Up</span>
          </div>
          {me && (
            <div className="topbar__user">
              {facility && (
                <span className="chip chip--dark">
                  <Icon name="building" size={14} />
                  {facility.name}
                </span>
              )}
              <span className="user">
                <span className="user__avatar" aria-hidden="true">{initials(me.user_id)}</span>
                <span className="user__text">
                  <span className="user__name">{me.user_id}</span>
                  <span className="user__role">
                    {ROLE_LABEL[me.role]}{me.can_write ? '' : ' · read-only'}
                  </span>
                </span>
              </span>
              <button type="button" className="btn btn--on-dark" onClick={onSignOut}>
                <Icon name="logout" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="main" id="main">{children}</main>
      <footer className="app-footer">
        <Icon name="shield" size={14} />
        Confidential health information. Do not share your screen or leave this computer unlocked.
      </footer>
    </div>
  );
}

function initials(userId: string): string {
  const parts = userId.split(/[._-]/).filter(Boolean);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?';
}
