// Base class for every screen (the old Page.java).

import { avatar, cancel, cooldownSeconds, request } from './api.js';
import { h } from './ui.js';
import { stopAllMedia } from './media.js';

export class Page {
  constructor(host) {
    this.host = host;
    this.active = false;
    this.sensitive = false;
    this.root = h('div', { class: 'page' });
  }

  view() {
    return this.root;
  }

  start() {
    this.active = true;
  }

  stop() {
    this.active = false;
    cancel(this);
  }

  dispose() {
    this.stop();
    stopAllMedia();
  }

  header(title, subtitle) {
    this.root.append(
      h('div', { class: 'page-header' }, h('h1', { text: title }), subtitle ? h('p', { class: 'txt muted small', text: subtitle }) : null),
    );
  }

  // A scrolling content area that fills the remaining height.
  form() {
    const content = h('div', { class: 'form' });
    this.root.append(h('div', { class: 'scroll' }, content));
    return content;
  }

  // Runs an API call for this page; ignores the answer if the page was left.
  async call(method, path, body) {
    try {
      const result = await request(this, method, path, body);
      return this.active ? result : undefined;
    } catch (error) {
      if (!this.active) return undefined;
      if (error.status === 401) {
        this.host.signIn();
        return undefined;
      }
      throw error;
    }
  }

  // Same as call() but shows the standard error dialog and resolves undefined on failure.
  async run(method, path, body) {
    try {
      return await this.call(method, path, body);
    } catch (error) {
      this.host.error(error);
      return undefined;
    }
  }

  async loadAvatar(username, version, apply) {
    if (!version) return;
    try {
      const url = await avatar(this, username, version);
      if (this.active && url) apply(url);
    } catch {
      /* avatars are optional */
    }
  }

  cooldown() {
    return cooldownSeconds();
  }
}

export const encode = encodeURIComponent;
