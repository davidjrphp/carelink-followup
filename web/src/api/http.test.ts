import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { ApiError, configureAuth, request } from './http';

describe('request()', () => {
  it('sends the bearer token and a correlation id', async () => {
    let auth: string | null = null;
    let cid: string | null = null;
    server.use(http.get('*/api/x', ({ request: r }) => {
      auth = r.headers.get('Authorization');
      cid = r.headers.get('X-Correlation-ID');
      return HttpResponse.json({ ok: true });
    }));
    configureAuth({ getToken: () => 'abc', onUnauthorized: () => undefined });
    await expect(request('/api/x')).resolves.toEqual({ ok: true });
    expect(auth).toBe('Bearer abc');
    expect(cid).toMatch(/^[0-9a-f]{12}$/);
  });

  it('turns the error shape into an ApiError with code, message, id and field details', async () => {
    server.use(http.get('*/api/x', () => HttpResponse.json({ error: {
      code: 'VALIDATION_FAILED', message: 'facility_id is required', correlation_id: '8c21-44f1',
      details: [{ field: 'facility_id', message: 'is required' }],
    } }, { status: 400 })));
    const err = await request('/api/x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 400, code: 'VALIDATION_FAILED', message: 'facility_id is required',
      correlationId: '8c21-44f1', details: [{ field: 'facility_id', message: 'is required' }] });
    expect((err as ApiError).retryable).toBe(false);
  });

  it('reports an unreachable server as a retryable network error', async () => {
    server.use(http.get('*/api/x', () => HttpResponse.error()));
    const err = (await request('/api/x').catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(0);
    expect(err.code).toBe('NETWORK_ERROR');
    expect(err.retryable).toBe(true);
  });

  it('treats a proxy 502 (API stopped) as unreachable, not as a server bug', async () => {
    server.use(http.get('*/api/x', () => new HttpResponse('<html>Bad Gateway</html>', { status: 502 })));
    const err = (await request('/api/x').catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(502);
    expect(err.unreachable).toBe(true);
    expect(err.retryable).toBe(true);
    expect(err.message).toMatch(/Can't reach the CareLink server/);
  });

  it('handles a non-JSON 500 page', async () => {
    server.use(http.get('*/api/x', () => new HttpResponse('oops', { status: 500 })));
    const err = (await request('/api/x').catch((e: unknown) => e)) as ApiError;
    expect(err.unreachable).toBe(false);
    expect(err.message).toMatch(/having a problem/);
  });

  it('signs the user out on 401', async () => {
    const onUnauthorized = vi.fn();
    configureAuth({ getToken: () => 'expired', onUnauthorized });
    server.use(http.get('*/api/x', () => HttpResponse.json(
      { error: { code: 'UNAUTHENTICATED', message: 'Sign in again.', correlation_id: 'x' } }, { status: 401 })));
    await expect(request('/api/x')).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it('encodes query parameters and drops empty ones', async () => {
    let url = '';
    server.use(http.get('*/api/x', ({ request: r }) => { url = r.url; return HttpResponse.json({}); }));
    await request('/api/x', { query: { q: "O'Brien & co", empty: '', none: undefined, n: 7 } });
    expect(new URL(url).search).toBe('?q=O%27Brien+%26+co&n=7');
  });
});
