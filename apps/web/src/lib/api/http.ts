import type { ApiError } from './types';

export class WorkbenchApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details: Record<string, unknown> = {}
  ) {
    super(message);
  }
}

export function queryString(
  values: Record<string, string | number | undefined>
): string {
  const parameters = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== '') parameters.set(key, String(value));
  }
  const encoded = parameters.toString();
  return encoded ? `?${encoded}` : '';
}

export async function apiGet<T>(
  path: string,
  values: Record<string, string | number | undefined> = {}
): Promise<T> {
  const response = await fetch(`${path}${queryString(values)}`, {
    headers: { Accept: 'application/json' }
  });
  if (!response.ok) {
    let error: ApiError | undefined;
    try {
      error = (await response.json()) as ApiError;
    } catch {
      error = undefined;
    }
    throw new WorkbenchApiError(
      error?.message ?? `La API respondió ${response.status}`,
      response.status,
      error?.code ?? 'api.unavailable',
      error?.details ?? {}
    );
  }
  return (await response.json()) as T;
}

export async function apiText(path: string): Promise<string> {
  const response = await fetch(path, { headers: { Accept: 'text/turtle' } });
  if (!response.ok)
    throw new WorkbenchApiError(
      'No se pudo cargar el RDF.',
      response.status,
      'api.unavailable'
    );
  return response.text();
}

export async function apiWrite<T>(
  path: string,
  method: 'POST' | 'PATCH' | 'DELETE',
  body: unknown
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    let error: ApiError | undefined;
    try {
      error = (await response.json()) as ApiError;
    } catch {
      error = undefined;
    }
    throw new WorkbenchApiError(
      error?.message ?? `La API respondió ${response.status}`,
      response.status,
      error?.code ?? 'api.unavailable',
      error?.details ?? {}
    );
  }
  return (await response.json()) as T;
}
