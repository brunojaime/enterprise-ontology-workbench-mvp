import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const proxy: RequestHandler = async ({ params, request, url, fetch }) => {
  const upstream = env.EOW_API_UPSTREAM_URL ?? 'http://127.0.0.1:8000';
  const target = new URL(`/api/${params.path}${url.search}`, upstream);
  const headers = new Headers(request.headers);
  headers.delete('host');
  const response = await fetch(target, {
    method: request.method,
    headers,
    body:
      request.method === 'GET' || request.method === 'HEAD'
        ? undefined
        : await request.arrayBuffer()
  });
  return new Response(response.body, {
    status: response.status,
    headers: response.headers
  });
};

export const GET = proxy;
export const POST = proxy;
