// API client. A faithful port of the old ApiClient.java:
// bounded concurrency, per-owner cancellation, deadlines, a persisted cooldown after
// 429/423, session clearing on 401, and no automatic retries.

import { apiOrigin } from './config.js';
import { isNative, nativeRequest, vault } from './native.js';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const MAX_BODY = 2 * 1024 * 1024;
const MAX_ACTIVE = 3;
const MAX_QUEUED = 24;
const DEADLINE_MS = 20000;
const PAUSE_KEY = 'wire.pause_until';
const EXPIRES_KEY = 'wire.expires';

// ------------------------------------------------------------------ session
export const session = {
  token: null,
  expires: 0,
  async load() {
    this.token = await vault.get('token').catch(() => null);
    this.expires = Number(localStorage.getItem(EXPIRES_KEY) || 0);
    if (!this.token) this.expires = 0;
  },
  valid() {
    return !!this.token && this.expires > Date.now() / 1000;
  },
  async save(token, expires) {
    await vault.set('token', token);
    this.token = token;
    this.expires = Number(expires);
    localStorage.setItem(EXPIRES_KEY, String(this.expires));
  },
  async savePendingRecovery(codes) {
    await vault.set('pending_recovery', JSON.stringify(codes));
  },
  async pendingRecovery() {
    try {
      const value = await vault.get('pending_recovery');
      return value ? JSON.parse(value) : null;
    } catch {
      await this.clearPendingRecovery();
      return null;
    }
  },
  async clearPendingRecovery() {
    await vault.remove('pending_recovery').catch(() => {});
  },
  async clear() {
    this.token = null;
    this.expires = 0;
    localStorage.removeItem(EXPIRES_KEY);
    await Promise.all([vault.remove('token'), vault.remove('pending_recovery')]).catch(() => {});
  },
};

// ----------------------------------------------------------------- cooldown
let cooldownUntil = Math.min(
  Number(localStorage.getItem(PAUSE_KEY) || 0),
  Date.now() + 2592000000,
);

export function cooldownSeconds() {
  return Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
}

function pauseRequests(seconds) {
  const ms = Math.max(1, Math.min(2592000, seconds)) * 1000;
  cooldownUntil = Date.now() + ms;
  localStorage.setItem(PAUSE_KEY, String(cooldownUntil));
}

// -------------------------------------------------------------- call control
const active = new Set();
const queue = [];
let closed = false;
let running = 0;

function pump() {
  while (running < MAX_ACTIVE && queue.length) {
    const job = queue.shift();
    if (job.call.cancelled) continue;
    running++;
    job.run().finally(() => {
      running--;
      pump();
    });
  }
}

export function cancel(owner) {
  for (const call of [...active]) {
    if (call.owner === owner) {
      call.cancel();
      active.delete(call);
    }
  }
}

export function cancelAll() {
  for (const call of active) call.cancel();
  active.clear();
  queue.length = 0;
}

// ------------------------------------------------------------------ request
const AUTH_PATH = /^\/v1\/auth\/(login|register|recover$|username)/;

function checkPath(path) {
  if (!path.startsWith('/v1/') || path.includes('..') || path.includes(':') || path.includes('\\')) {
    throw new ApiError(0, 'Invalid request');
  }
}

function precheck(path) {
  checkPath(path);
  if (cooldownSeconds() > 0) {
    throw new ApiError(429, 'Please wait ' + cooldownSeconds() + ' seconds');
  }
  const authPath = AUTH_PATH.test(path);
  if (!authPath && !session.valid()) {
    session.clear();
    throw new ApiError(401, 'Please sign in again');
  }
  return authPath;
}

async function transport(call, method, path, body, wantBytes) {
  const url = apiOrigin() + path;
  const headers = { Accept: wantBytes ? 'image/webp' : 'application/json' };
  if (session.token && !AUTH_PATH.test(path)) headers.Authorization = 'Bearer ' + session.token;
  if (body !== undefined && body !== null) headers['Content-Type'] = 'application/json';

  if (isNative) {
    const r = await nativeRequest({
      method,
      url,
      headers,
      body: body ?? undefined,
      timeoutMs: 15000,
      responseType: wantBytes ? 'blob' : 'text',
    });
    return r;
  }
  const controller = new AbortController();
  call.abort = () => controller.abort();
  const response = await fetch(url, {
    method,
    headers,
    body: body == null ? undefined : JSON.stringify(body),
    redirect: 'error',
    signal: controller.signal,
    cache: 'no-store',
  });
  const lower = {};
  response.headers.forEach((v, k) => (lower[k.toLowerCase()] = v));
  if (wantBytes) {
    const blob = await response.blob();
    return { status: response.status, headers: lower, data: blob };
  }
  return { status: response.status, headers: lower, data: await response.text() };
}

function parse(data) {
  if (data === null || data === undefined || data === '') return {};
  if (typeof data === 'string') {
    if (data.length > MAX_BODY) throw new Error('Response too large');
    return JSON.parse(data);
  }
  return data; // native layer already parsed JSON
}

function messageFrom(data, fallback) {
  try {
    const value = parse(data);
    if (value && typeof value.detail === 'string') return value.detail;
  } catch {
    /* not JSON */
  }
  return fallback;
}

function submit(owner, method, path, body, wantBytes) {
  if (closed) return Promise.reject(new ApiError(0, 'Closed'));
  let authPath;
  try {
    authPath = precheck(path);
  } catch (error) {
    return Promise.reject(error);
  }
  void authPath;
  return new Promise((resolve, reject) => {
    const call = {
      owner,
      cancelled: false,
      abort: null,
      timer: null,
      cancel() {
        this.cancelled = true;
        if (this.abort) this.abort();
        clearTimeout(this.timer);
      },
    };
    if (queue.length >= MAX_QUEUED) {
      reject(new ApiError(0, 'Please wait for the current requests to finish'));
      return;
    }
    active.add(call);
    const run = async () => {
      try {
        if (call.cancelled || closed) return;
        if (cooldownSeconds() > 0) throw new ApiError(429, 'Please wait ' + cooldownSeconds() + ' seconds');
        call.timer = setTimeout(() => call.cancel(), DEADLINE_MS);
        const r = await transport(call, method, path, body, wantBytes);
        if (call.cancelled) return;
        if (r.status === 429 || r.status === 423) {
          const delay = parseInt(r.headers['retry-after'], 10);
          pauseRequests(Number.isFinite(delay) ? delay : 60);
          for (const other of [...active]) {
            if (other !== call) {
              other.cancel();
              active.delete(other);
            }
          }
        }
        if (r.status < 200 || r.status >= 300) {
          if (r.status === 401) await session.clear();
          const text = typeof r.data === 'string' || (r.data && typeof r.data === 'object' && !(r.data instanceof Blob)) ? r.data : '';
          throw new ApiError(r.status, messageFrom(text, 'Request failed (' + r.status + ')'));
        }
        resolve(wantBytes ? r : parse(r.data));
      } catch (error) {
        if (call.cancelled) return;
        reject(error instanceof ApiError ? error : new ApiError(0, 'Connection interrupted. Check your connection and try again.'));
      } finally {
        clearTimeout(call.timer);
        active.delete(call);
      }
    };
    queue.push({ call, run });
    pump();
  });
}

export function request(owner, method, path, body) {
  return submit(owner, method, path, body, false);
}

// ------------------------------------------------------------- avatar images
const images = new Map(); // "user:version" -> data URL
let imageBytes = 0;

export function clearImages() {
  images.clear();
  imageBytes = 0;
}

function toDataUrl(r) {
  if (typeof r.data === 'string') {
    const type = r.headers['content-type'] || 'image/webp';
    return Promise.resolve('data:' + type.split(';')[0] + ';base64,' + r.data);
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(r.data);
  });
}

export async function avatar(owner, username, version) {
  const key = username + ':' + version;
  if (images.has(key)) return images.get(key);
  const r = await submit(owner, 'GET', '/v1/users/' + encodeURIComponent(username) + '/avatar', undefined, true);
  const url = await toDataUrl(r);
  if (url.length > 400000) return url; // never cache oversized payloads
  images.set(key, url);
  imageBytes += url.length;
  while (imageBytes > 2 * 1024 * 1024 && images.size) {
    const oldest = images.keys().next().value;
    imageBytes -= images.get(oldest).length;
    images.delete(oldest);
  }
  return url;
}

export function closeClient() {
  closed = true;
  cancelAll();
}
