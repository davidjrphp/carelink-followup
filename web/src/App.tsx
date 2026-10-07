import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { ApiError } from './api/http';
import { SignInPage } from './auth/SignInPage';
import { SessionProvider, useSession } from './auth/session';
import { AppShell } from './components/AppShell';
import { ErrorState, LoadingRows } from './components/StateViews';
import { FollowUpPage } from './features/followup/FollowUpPage';
import { useFacilities, useMe } from './features/followup/queries';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Retry only what can succeed unchanged (network, 429, 5xx); a 400 or 403 will not.
        retry: (count, error) => error instanceof ApiError && error.retryable && count < 2,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
        // No background polling or refetch-on-focus: clinic bandwidth is scarce (review item C2 #4).
        refetchOnWindowFocus: false,
      },
      mutations: {
        // Writes carry an Idempotency-Key, so a retry after a time-out cannot record twice.
        // Jitter spreads retries when many clinics reconnect at once.
        retry: (count, error) => error instanceof ApiError && error.retryable && count < 3,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000) + Math.random() * 500,
      },
    },
  });
}

export function App({ queryClient }: { queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <QueryClientProvider client={client}>
      <SessionProvider>
        <Root />
      </SessionProvider>
    </QueryClientProvider>
  );
}

function Root() {
  const { token, signOut } = useSession();
  const me = useMe(token !== null);
  const facilities = useFacilities(token !== null);

  if (token === null) return <SignInPage />;

  const facility = facilities.data?.find((f) => f.facility_id === me.data?.facility_id);
  const failed = me.error ?? facilities.error;
  return (
    <AppShell me={me.data ?? null} facility={facility} onSignOut={() => signOut()}>
      {failed ? (
        <ErrorState error={failed} retrying={me.isFetching || facilities.isFetching}
          onRetry={() => { void me.refetch(); void facilities.refetch(); }} />
      ) : me.data && facilities.data ? (
        <FollowUpPage me={me.data} facilities={facilities.data} />
      ) : (
        <div className="page-loading" aria-busy="true">
          <p className="sr-only" role="status">Loading…</p>
          <LoadingRows rows={6} />
        </div>
      )}
    </AppShell>
  );
}
