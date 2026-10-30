// Where the Wire API lives. Set VITE_API_URL when building (build-apk.bat does it).
// Same rules the old native app enforced: https only, a bare origin, no credentials.

export const isDevBrowser = import.meta.env.DEV;

export function validateOrigin(input) {
  if (typeof input !== 'string' || input.length > 512) throw new Error('Invalid server address');
  let value = input.trim();
  while (value.endsWith('/')) value = value.slice(0, -1);
  let u;
  try {
    u = new URL(value);
  } catch {
    throw new Error('Enter an origin such as https://your-wire-api.onrender.com');
  }
  if (
    u.protocol !== 'https:' ||
    !u.hostname ||
    u.username ||
    u.password ||
    u.search ||
    u.hash ||
    (u.pathname && u.pathname !== '/')
  ) {
    throw new Error('Use a plain https:// server address without a path');
  }
  return u.origin;
}

// In `npm run dev` the browser talks to the Vite proxy (same origin, no CORS).
export function apiOrigin() {
  if (isDevBrowser) return '';
  return validateOrigin(import.meta.env.VITE_API_URL || '');
}

export const APP_VERSION = '1.0.0';
