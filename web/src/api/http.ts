import type { ApiErrorBody, FieldError } from './types';

/** Every failure the UI can see is an ApiError, including "the server is unreachable". */
export class ApiError extends Error {
  constructor(
    public readonly status: number, // 0 = network failure or timeout
    public readonly code: string,
    message: string,
    public readonly correlationId: string | null = null,
    public readonly details: FieldError[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** Worth retrying automatically: the request may succeed if sent again unchanged. */
  get retryable(): boolean {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }

  /** The API could not be reached: no network, or a gateway reporting the API is down. */
  get unreachable(): boolean {
    return this.code === 'NETWORK_ERROR' || this.code === 'GATEWAY_ERROR';
  }
}

const GATEWAY_STATUSES = [502, 503, 504];

export const NETWORK_MESSAGE =
  "Can't reach the CareLink server. Check the connection, then try again.";

const REQUEST_TIMEOUT_MS = 20_000;

interface AuthHooks {
  getToken: () => string | null;
  onUnauthorized: () => void;
}

let auth: AuthHooks = { getToken: () => null, onUnauthorized: () => undefined };

export function configureAuth(hooks: AuthHooks): void {
  auth = hooks;
}

type QueryValue = string | number | undefined | null;

export interface RequestOptions {
  method?: 'GET' | 'POST';
  query?: Record<string, QueryValue>;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Use this token instead of the session's (sign-in checks a token before storing it). */
  token?: string;
}

export function newId(): string {
  // crypto.randomUUID needs a secure context; fall back for plain-HTTP clinic LANs.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const qs = params.toString();
  return new URL(qs ? `${path}?${qs}` : path, window.location.href).toString();
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const err = (value as { error: unknown }).error;
  return typeof err === 'object' && err !== null && 'code' in err && 'message' in err;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const correlationId = newId().replace(/-/g, '').slice(0, 12);
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Correlation-ID': correlationId,
    ...options.headers,
  };
  const token = options.token ?? auth.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  // A hung request must end in an error state with a retry, never an endless spinner.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const onCallerAbort = () => controller.abort();
  options.signal?.addEventListener('abort', onCallerAbort);

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
      credentials: 'omit',
    });
  } catch (cause) {
    if (options.signal?.aborted) throw cause; // superseded by a newer request; not an error to show
    throw new ApiError(0, 'NETWORK_ERROR', NETWORK_MESSAGE, correlationId);
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', onCallerAbort);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null; // e.g. an HTML error page from a proxy; handled below
  }

  if (!response.ok) {
    if (response.status === 401 && options.token === undefined) auth.onUnauthorized();
    if (isErrorBody(payload)) {
      const { code, message, correlation_id, details } = payload.error;
      throw new ApiError(response.status, code, message, correlation_id, details ?? []);
    }
    // No error body: the request never reached the API (e.g. the proxy's 502 when the API is down).
    const gateway = GATEWAY_STATUSES.includes(response.status);
    const fallback = gateway
      ? NETWORK_MESSAGE
      : response.status >= 500
        ? 'The CareLink server is having a problem. Try again in a moment.'
        : `The request failed (HTTP ${response.status}).`;
    throw new ApiError(response.status, gateway ? 'GATEWAY_ERROR' : 'HTTP_ERROR', fallback,
      response.headers.get('X-Correlation-ID') ?? correlationId);
  }
  return payload as T;
}
