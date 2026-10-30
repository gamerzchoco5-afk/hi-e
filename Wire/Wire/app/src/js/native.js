// Thin wrappers around Capacitor so the rest of the app never touches plugins directly.
// Every call also has a browser fallback so `npm run dev` works on a desktop.

import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Clipboard } from '@capacitor/clipboard';
import { Share } from '@capacitor/share';

export const isNative = Capacitor.isNativePlatform();
const Vault = isNative ? registerPlugin('WireVault') : null;
const Guard = isNative ? registerPlugin('ScreenGuard') : null;

// ---- secure storage (Android Keystore on the phone, localStorage only in browser dev)
export const vault = {
  async get(key) {
    if (Vault) return (await Vault.getItem({ key })).value ?? null;
    return localStorage.getItem('dev_vault_' + key);
  },
  async set(key, value) {
    if (Vault) return Vault.setItem({ key, value });
    localStorage.setItem('dev_vault_' + key, value);
  },
  async remove(key) {
    if (Vault) return Vault.removeItem({ key });
    localStorage.removeItem('dev_vault_' + key);
  },
};

export function setSecureScreen(secure) {
  if (Guard) Guard.setSecure({ secure }).catch(() => {});
}

// ---- native HTTP (no browser CORS, same as the old HttpURLConnection client)
export async function nativeRequest({ method, url, headers, body, timeoutMs, responseType }) {
  const response = await CapacitorHttp.request({
    method,
    url,
    headers,
    data: body === undefined ? undefined : body,
    responseType: responseType || 'text',
    connectTimeout: 10000,
    readTimeout: timeoutMs || 15000,
    disableRedirects: true,
  });
  const lower = {};
  for (const [k, v] of Object.entries(response.headers || {})) lower[k.toLowerCase()] = v;
  return { status: response.status, headers: lower, data: response.data };
}

// ---- app lifecycle and system actions
export function onBackButton(handler) {
  if (!isNative) return;
  App.addListener('backButton', handler);
}

export function onActiveChange(handler) {
  if (isNative) App.addListener('appStateChange', (s) => handler(s.isActive));
  else document.addEventListener('visibilitychange', () => handler(!document.hidden));
}

export function exitApp() {
  if (isNative) App.exitApp();
}

export async function openExternal(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol !== 'https:') return false;
  if (isNative) await Browser.open({ url: parsed.href });
  else window.open(parsed.href, '_blank', 'noopener,noreferrer');
  return true;
}

export async function shareText(text) {
  try {
    if (isNative) await Share.share({ text, dialogTitle: 'Share post' });
    else if (navigator.share) await navigator.share({ text });
    else await navigator.clipboard.writeText(text);
  } catch {
    /* user cancelled */
  }
}

// Copies sensitive text and clears it from the clipboard after a minute (if unchanged).
export async function copySensitive(text) {
  const write = (value) =>
    isNative ? Clipboard.write({ string: value }) : navigator.clipboard.writeText(value);
  await write(text);
  setTimeout(async () => {
    try {
      const current = isNative
        ? (await Clipboard.read()).value
        : await navigator.clipboard.readText();
      if (current === text) await write('');
    } catch {
      /* clipboard not readable */
    }
  }, 60000);
}
