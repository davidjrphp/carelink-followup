import { useId, useState, type FormEvent } from 'react';
import { ApiError } from '../api/http';
import { followUpService } from '../api/followUpService';
import { Icon, LogoMark } from '../components/Icon';
import { DEMO_ACCOUNTS } from './demoAccounts';
import { useSession } from './session';

/**
 * Assessment-only sign-in: pick a demo account (a static token mapped to a role and facility).
 * In production this page is replaced by a redirect to the OIDC provider (Keycloak).
 */
export function SignInPage() {
  const { signIn, signOutReason } = useSession();
  const tokenId = useId();
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function attempt(candidate: string) {
    setBusy(true);
    setError(null);
    // Check the token before storing it, so a typo gives a clear message instead of a broken screen.
    try {
      await followUpService.getMe(undefined, candidate);
      signIn(candidate);
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      setError(err?.status === 401 ? 'That access token was not recognised.' : err?.message ?? 'Sign-in failed.');
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) {
      setError('Enter an access token, or choose a demo account.');
      return;
    }
    void attempt(token.trim());
  }

  return (
    <div className="signin">
      <div className="signin__panel">
        <div className="signin__brand">
          <LogoMark size={40} />
          <div>
            <p className="signin__product">CareLink</p>
            <p className="signin__module">Follow-Up</p>
          </div>
        </div>
        <h1 className="signin__title">Sign in</h1>
        <p className="signin__lead">Find patients who missed appointments and record contact attempts.</p>

        {signOutReason && <div className="alert alert--info" role="status"><Icon name="clock" />{signOutReason}</div>}
        {error && <div className="alert alert--danger" role="alert"><Icon name="alert" />{error}</div>}

        <h2 className="signin__section">Demo accounts</h2>
        <ul className="account-list">
          {DEMO_ACCOUNTS.map((a) => (
            <li key={a.token}>
              <button type="button" className="account" onClick={() => void attempt(a.token)} disabled={busy}>
                <span className="account__label">{a.label}</span>
                <span className="account__desc">{a.description}</span>
                <span className="account__go" aria-hidden="true">→</span>
              </button>
            </li>
          ))}
        </ul>

        <details className="signin__manual">
          <summary>Use an access token instead</summary>
          <form onSubmit={onSubmit} noValidate>
            <div className="field">
              <label htmlFor={tokenId}>Access token</label>
              <input id={tokenId} type="password" autoComplete="off" value={token}
                onChange={(e) => setToken(e.target.value)} />
            </div>
            <button type="submit" className="btn btn--primary" disabled={busy}>Sign in</button>
          </form>
        </details>

        <p className="signin__note">
          <Icon name="shield" size={14} />
          Demo sign-in for the assessment. Production uses single sign-on with personal accounts.
        </p>
      </div>
    </div>
  );
}
