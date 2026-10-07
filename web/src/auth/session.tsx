import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { configureAuth } from '../api/http';

// sessionStorage, not localStorage: the token dies with the tab on a shared clinic PC (Section D2).
// In production this is replaced by an OIDC login with short-lived tokens held in memory.
const KEY = 'carelink.session';

function readToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

interface Session {
  token: string | null;
  signIn: (token: string) => void;
  signOut: (reason?: string) => void;
  signOutReason: string | null;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(readToken);
  const [signOutReason, setSignOutReason] = useState<string | null>(null);

  const signOut = useCallback((reason?: string) => {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* storage unavailable: nothing to clear */
    }
    queryClient.clear(); // no patient data survives sign-out
    setSignOutReason(reason ?? null);
    setToken(null);
  }, [queryClient]);

  const signIn = useCallback((next: string) => {
    try {
      sessionStorage.setItem(KEY, next);
    } catch {
      /* keep the session in memory only */
    }
    setSignOutReason(null);
    setToken(next);
  }, []);

  // Registered during render (idempotent), so the first queries after sign-in carry the token.
  configureAuth({
    getToken: () => token,
    onUnauthorized: () => signOut('Your session has ended. Sign in again to continue.'),
  });

  const value = useMemo(() => ({ token, signIn, signOut, signOutReason }),
    [token, signIn, signOut, signOutReason]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>');
  return ctx;
}
