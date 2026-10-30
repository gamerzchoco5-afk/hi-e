// Chat conversation screen and the inbox.

import { cooldownSeconds } from '../api.js';
import { Page, encode } from '../page.js';
import { actionButton, button, choose, confirm, formatTime, h, info, input, linkify, prompt, text } from '../ui.js';
import { createMedia, stopAllMedia } from '../media.js';

export class ChatPage extends Page {
  constructor(host, id, username) {
    super(host);
    this.id = id;
    this.username = username;
    this.messages = new Map();
    this.loading = false;
    this.accepted = false;
    this.incoming = false;
    this.peerRead = 0;
    this.lastReadSent = 0;
    this.clientId = crypto.randomUUID();
    this.timer = null;

    this.root.append(
      h('div', { class: 'row toolbar' },
        actionButton('‹', () => host.navigate(new Inbox(host), 3)),
        h('strong', { class: 'grow', text: '@' + username, onClick: () => host.profile(username) }),
        actionButton('•••', async () => {
          const which = await choose(['View profile', 'Report conversation']);
          if (which === 0) host.profile(username);
          else if (which === 1) {
            const reason = await prompt('Report conversation', 'What happened?');
            if (reason !== null && (await this.run('PUT', '/v1/conversations/' + this.id + '/report', { reason }))) {
              info('Report submitted', 'Your report has been recorded.');
            }
          }
        })),
    );
    this.status = text('Connecting…', 'small muted pad');
    this.accept = button('Accept message request', async () => {
      if (await this.run('PUT', '/v1/conversations/' + this.id + '/accept')) this.poll(false);
    }, 'primary');
    this.accept.hidden = true;
    this.transcript = h('div', { class: 'transcript' });
    this.scroll = h('div', { class: 'scroll' }, this.transcript);
    this.draft = input('Message', { multiline: true });
    this.draft.rows = 1;
    this.send = button('Send', () => this.sendMessage(), 'primary');
    this.root.append(this.status, this.accept, button('Load earlier messages', () => this.poll(true)), this.scroll,
      h('div', { class: 'row pad composer' }, this.draft, this.send));
  }
  start() {
    super.start();
    this.loading = false;
    this.send.disabled = false;
    this.poll(false);
  }
  stop() {
    clearTimeout(this.timer);
    stopAllMedia();
    this.loading = false;
    super.stop();
  }
  schedule(delay) {
    clearTimeout(this.timer);
    if (this.active) this.timer = setTimeout(() => this.poll(false), delay);
  }
  async poll(earlier) {
    if (!this.active || this.loading) return;
    if (cooldownSeconds() > 0) {
      this.status.hidden = false;
      this.status.textContent = 'Requests paused · ' + cooldownSeconds() + ' seconds';
      this.schedule(1000);
      return;
    }
    this.loading = true;
    clearTimeout(this.timer);
    const keys = [...this.messages.keys()];
    const path = '/v1/conversations/' + this.id + '/messages?limit=40' + (earlier && keys.length ? '&before=' + Math.min(...keys) : '');
    try {
      const r = await this.call('GET', path);
      this.loading = false;
      if (!r) return;
      this.accepted = !!r.accepted;
      this.incoming = !!r.is_request;
      const previousRead = this.peerRead;
      this.peerRead = r.peer_read || 0;
      let changed = previousRead !== this.peerRead || this.messages.size === 0;
      for (const m of r.items || []) {
        const old = this.messages.get(m.id);
        this.messages.set(m.id, m);
        changed = changed || !old || JSON.stringify(old) !== JSON.stringify(m);
      }
      while (this.messages.size > 300) this.messages.delete(Math.min(...this.messages.keys()));
      this.accept.hidden = !this.incoming;
      this.send.disabled = !(this.accepted || (!this.incoming && this.messages.size === 0));
      this.status.hidden = this.accepted;
      this.status.textContent = this.accepted
        ? 'Messages are encrypted in transit. They are not end-to-end encrypted.'
        : this.incoming ? 'Message request · Accept to reply.' : 'You can send one message while your request is pending.';
      if (changed) this.render(!earlier);
      const keysNow = [...this.messages.keys()];
      const last = keysNow.length ? Math.max(...keysNow) : 0;
      if (last > this.lastReadSent) {
        this.call('PUT', '/v1/conversations/' + this.id + '/read', { message_id: last })
          .then(() => (this.lastReadSent = last)).catch(() => {});
      }
      this.schedule(5000);
    } catch (error) {
      this.loading = false;
      this.status.hidden = false;
      this.status.textContent = error.message;
      this.schedule(error.status === 429 || error.status === 423 ? 1000 : 15000);
    }
  }
  render(latest) {
    const box = this.scroll;
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 80;
    stopAllMedia();
    const bubbles = [...this.messages.entries()].sort((a, b) => a[0] - b[0]).map(([id, m]) => {
      const own = !!m.is_me;
      const bubble = h('div', { class: 'bubble ' + (own ? 'own' : 'peer') },
        h('p', { class: 'selectable' }, m.deleted ? 'Message deleted' : linkify(m.body || '')));
      if (!m.deleted) {
        const media = createMedia(m.body || '');
        if (media) bubble.append(media);
      }
      let time = formatTime(m.created_at);
      if (own && this.peerRead >= id) time += ' · Seen';
      bubble.append(h('span', { class: 'tiny muted', text: time }));
      if (own && !m.deleted) {
        let pressTimer;
        const ask = async () => {
          if (await confirm('Delete this message for both people?', 'Delete')) {
            if (await this.run('DELETE', '/v1/messages/' + m.id)) { m.deleted = true; this.render(false); }
          }
        };
        bubble.addEventListener('contextmenu', (e) => { e.preventDefault(); ask(); });
        bubble.addEventListener('touchstart', () => (pressTimer = setTimeout(ask, 600)), { passive: true });
        for (const ev of ['touchend', 'touchmove', 'touchcancel']) bubble.addEventListener(ev, () => clearTimeout(pressTimer), { passive: true });
      }
      return bubble;
    });
    this.transcript.replaceChildren(...bubbles);
    if (latest && atBottom) requestAnimationFrame(() => (box.scrollTop = box.scrollHeight));
  }
  async sendMessage() {
    const body = this.draft.value.trim();
    if (!body) return;
    this.send.disabled = true;
    const r = await this.run('POST', '/v1/conversations/' + this.id + '/messages', { body, client_id: this.clientId });
    if (!r) { this.send.disabled = false; return; }
    this.draft.value = '';
    this.clientId = crypto.randomUUID();
    this.messages.set(r.id, r);
    this.render(true);
    this.send.disabled = !this.accepted;
    this.schedule(100);
  }
}

export class Inbox extends Page {
  constructor(host) {
    super(host);
    this.offset = null;
    this.header('Your inbox.', 'Keep the conversation going.');
    this.root.append(h('div', { class: 'row pad' },
      button('Refresh', () => this.load(true)),
      button('New message', async () => {
        const name = await prompt('New message', 'Username without @');
        if (name === null) return;
        const username = name.trim().toLowerCase();
        const r = await this.run('POST', '/v1/conversations', { username });
        if (r) host.navigate(new ChatPage(host, r.id, username), 3);
      }, 'primary')));
    this.list = this.form();
    this.root.append(button('Load more', () => this.load(false)));
  }
  start() {
    super.start();
    this.load(true);
  }
  async load(reset) {
    if (!reset && this.offset === null) return;
    const r = await this.run('GET', '/v1/conversations?limit=20&offset=' + (reset ? 0 : this.offset));
    if (!r) return;
    if (reset) this.list.replaceChildren();
    for (const c of r.items || []) {
      const last = c.last_message;
      const preview = !last ? 'Start a conversation' : last.deleted ? 'Message deleted' : last.body;
      this.list.append(h('button', { type: 'button', class: 'btn convo', onClick: () => this.host.navigate(new ChatPage(this.host, c.id, c.username), 3) },
        h('strong', { text: c.display_name + ' · @' + c.username + (c.unread_count > 0 ? ' · ' + c.unread_count + ' new' : '') }),
        c.is_request ? h('span', { class: 'small accent', text: 'Message request' }) : null,
        h('span', { class: 'small muted preview', text: preview })));
    }
    if (reset && !(r.items || []).length) this.list.append(text('No messages yet. Find someone and say hello.', 'muted'));
    this.offset = r.next_offset ?? null;
  }
}
void encode;
