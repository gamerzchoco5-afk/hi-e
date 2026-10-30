// Tiny DOM helpers and dialogs. All text goes through textContent, never innerHTML,
// so user-written posts and names can never inject markup.

import { openExternal } from './native.js';

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

export const button = (label, onClick, kind = '') =>
  h('button', { type: 'button', class: 'btn ' + kind, onClick }, label);

export const actionButton = (label, onClick, selected = false) =>
  h('button', { type: 'button', class: 'act' + (selected ? ' on' : ''), onClick }, label);

export function input(placeholder, { password = false, multiline = false, type = 'text', value = '' } = {}) {
  const el = multiline
    ? h('textarea', { class: 'field', placeholder, rows: 3 })
    : h('input', {
        class: 'field',
        placeholder,
        type: password ? 'password' : type,
        autocomplete: password ? 'current-password' : 'off',
        autocapitalize: 'none',
        spellcheck: 'false',
      });
  el.value = value;
  return el;
}

export const text = (value, cls = '') => h('p', { class: 'txt ' + cls, text: value });

// ---- links: only https URLs become tappable, and they open outside the app
const URL_RE = /https:\/\/[^\s<>]+/gi;

export function linkify(value) {
  const nodes = [];
  let last = 0;
  for (const match of value.matchAll(URL_RE)) {
    const raw = match[0];
    const url = raw.replace(/[),.!?]+$/, '');
    nodes.push(document.createTextNode(value.slice(last, match.index)));
    nodes.push(
      h('a', {
        href: '#',
        class: 'link',
        text: url,
        onClick: (event) => {
          event.preventDefault();
          event.stopPropagation();
          openExternal(url);
        },
      }),
    );
    nodes.push(document.createTextNode(raw.slice(url.length)));
    last = match.index + raw.length;
  }
  nodes.push(document.createTextNode(value.slice(last)));
  return nodes;
}

// ---------------------------------------------------------------- dialogs
function overlay(content, onClose) {
  const backdrop = h('div', { class: 'overlay', role: 'dialog', 'aria-modal': 'true' }, content);
  const close = () => {
    backdrop.remove();
    if (onClose) onClose();
  };
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) close();
  });
  document.getElementById('overlays').append(backdrop);
  return close;
}

export function dialog({ title, message, actions }) {
  return new Promise((resolve) => {
    let close;
    const done = (value) => {
      close();
      resolve(value);
    };
    const box = h(
      'div',
      { class: 'dialog' },
      title ? h('h3', { text: title }) : null,
      message ? h('p', { class: 'dialog-msg', text: message }) : null,
      h(
        'div',
        { class: 'dialog-actions' },
        actions.map((a) => h('button', { type: 'button', class: 'btn ' + (a.kind || ''), onClick: () => done(a.value) }, a.label)),
      ),
    );
    close = overlay(box, () => resolve(undefined));
  });
}

export const info = (title, message) => dialog({ title, message, actions: [{ label: 'OK', value: true, kind: 'primary' }] });

export async function confirm(message, okLabel = 'Continue', title = '') {
  const result = await dialog({
    title,
    message,
    actions: [
      { label: 'Cancel', value: false },
      { label: okLabel, value: true, kind: 'primary' },
    ],
  });
  return result === true;
}

export function prompt(title, hint, password = false) {
  return new Promise((resolve) => {
    const field = input(hint, { password });
    let close;
    const done = (value) => {
      close();
      resolve(value);
    };
    const box = h(
      'div',
      { class: 'dialog' },
      h('h3', { text: title }),
      field,
      h(
        'div',
        { class: 'dialog-actions' },
        button('Cancel', () => done(null)),
        button('Continue', () => done(field.value), 'primary'),
      ),
    );
    close = overlay(box, () => resolve(null));
    setTimeout(() => field.focus(), 50);
  });
}

// A list of choices; resolves with the chosen index or -1.
export function choose(labels) {
  return new Promise((resolve) => {
    let close;
    const done = (value) => {
      close();
      resolve(value);
    };
    const box = h(
      'div',
      { class: 'dialog' },
      labels.map((label, index) => h('button', { type: 'button', class: 'btn', onClick: () => done(index) }, label)),
    );
    close = overlay(box, () => resolve(-1));
  });
}

// ------------------------------------------------------------------ icons
const ICONS = {
  home: '<path d="M3 12 14 3l11 9M6 10v15h16V10M11 25v-8h6v8"/>',
  search: '<circle cx="12" cy="12" r="8"/><path d="m18 18 7 7"/>',
  plus: '<path d="M4 14h20M14 4v20"/>',
  inbox: '<rect x="3" y="4" width="22" height="17" rx="5"/><path d="M8 21v5l6-5M8 10h12M8 15h8"/>',
  me: '<circle cx="14" cy="9" r="5"/><path d="M4 26a10 10 0 0 1 20 0"/>',
};

export function icon(name) {
  const wrapper = document.createElement('span');
  wrapper.className = 'icon';
  wrapper.innerHTML =
    '<svg viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    ICONS[name] + // fixed internal markup only, never user data
    '</svg>';
  return wrapper;
}

export function formatTime(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function formatDateTime(seconds) {
  return new Date(seconds * 1000).toLocaleString();
}
