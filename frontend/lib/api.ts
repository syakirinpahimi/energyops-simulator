/**
 * Tiny typed fetch wrapper around the FastAPI backend.
 *
 * - Reads the JWT from localStorage so the same client works in pages and
 *   client components without prop-drilling auth.
 * - Returns parsed JSON or throws an ``ApiError`` carrying the backend's
 *   ``{error: {code, message}}`` envelope.
 * - All callers go through this so adding observability or refresh logic
 *   later is a one-file change.
 * - When ``NEXT_PUBLIC_USE_MOCKS=1`` the request is short-circuited via
 *   the mock layer for offline UI development.
 */

import { isMockEnabled, mockFetch } from "./api.mock";

const TOKEN_KEY = "energyops.jwt";

const BASE_URL =
  (typeof process !== "undefined" &&
    (process.env.NEXT_PUBLIC_API_BASE_URL ||
      process.env.NEXT_PUBLIC_API_URL)) ||
  "";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// Alias used by newer pages; kept as the canonical name going forward.
export const ApiRequestError = ApiError;

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type FetchInit = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  // Skip Authorization header (e.g. login).
  unauth?: boolean;
};

function buildUrl(path: string, query?: FetchInit["query"]): string {
  const base = path.startsWith("/") ? path : `/${path}`;
  const apiPath = base.startsWith("/api/") || base.startsWith("http") ? base : `/api${base}`;
  const url = apiPath.startsWith("http")
    ? apiPath
    : `${BASE_URL}${apiPath}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function api<T = unknown>(path: string, init: FetchInit = {}): Promise<T> {
  if (isMockEnabled()) {
    const sanitisedQuery = init.query
      ? Object.fromEntries(
          Object.entries(init.query).map(([k, v]) => [
            k,
            typeof v === "boolean" ? String(v) : v
          ])
        )
      : undefined;
    return mockFetch<T>(path, {
      method: (init.method as "GET" | "POST" | "PATCH" | "DELETE" | undefined) ?? "GET",
      body: init.body,
      query: sanitisedQuery
    });
  }

  const { body, query, headers, unauth, ...rest } = init;
  const isJson = body !== undefined && !(body instanceof FormData);
  const resp = await fetch(buildUrl(path, query), {
    ...rest,
    headers: {
      ...(isJson ? { "Content-Type": "application/json" } : {}),
      ...(unauth ? {} : authHeaders()),
      ...(headers || {}),
    },
    body: isJson ? JSON.stringify(body) : (body as BodyInit | undefined),
  });

  if (!resp.ok) {
    let code = "ERROR";
    let message = `Request failed with status ${resp.status}`;
    let details: unknown;
    try {
      const data = await resp.json();
      const env = data?.error;
      if (env) {
        code = env.code || code;
        message = env.message || message;
        details = env.details;
      }
    } catch {
      // non-JSON error body, ignore
    }
    if (resp.status === 401) {
      setToken(null);
    }
    throw new ApiError(resp.status, code, message, details);
  }

  if (resp.status === 204) return undefined as T;
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await resp.json()) as T;
  return (await resp.text()) as unknown as T;
}

/** Build a download URL that includes the JWT in the Authorization header. */
export async function downloadFile(path: string, query: FetchInit["query"], filename: string): Promise<void> {
  const resp = await fetch(buildUrl(path, query), { headers: authHeaders() });
  if (!resp.ok) {
    let message = `Download failed (${resp.status})`;
    try {
      const data = await resp.json();
      message = data?.error?.message || message;
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, "DOWNLOAD_FAILED", message);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
