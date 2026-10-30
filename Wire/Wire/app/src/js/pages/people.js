// People search, followers/following lists and the blocked-accounts list.

import { Page, encode } from '../page.js';
import { button, h, input, text } from '../ui.js';

export class PeoplePage extends Page {
  constructor(host, fixedPath = null, title = 'Find your people.') {
    super(host);
    this.fixedPath = fixedPath;
    this.cursor = null;
    this.header(title, fixedPath === null ? 'A username, a familiar face, a new point of view.' : null);
    this.query = input('Search names or usernames');
    if (fixedPath === null) {
      this.query.addEventListener('keydown', (e) => e.key === 'Enter' && this.load(true));
      this.root.append(h('div', { class: 'pad' }, this.query, button('Search', () => this.load(true), 'primary')));
    }
    this.results = h('div', { class: 'form' });
    this.root.append(h('div', { class: 'scroll' }, this.results), button('Load more', () => this.load(false)));
  }
  start() {
    super.start();
    this.load(true);
  }
  async load(reset) {
    if (!reset && this.cursor === null) return;
    let path = this.fixedPath === null ? '/v1/users?q=' + encode(this.query.value) : this.fixedPath;
    path += (path.includes('?') ? '&' : '?') + 'limit=20' + (!reset ? '&cursor=' + encode(this.cursor) : '');
    const r = await this.run('GET', path);
    if (!r) return;
    if (reset) this.results.replaceChildren();
    const blocked = this.fixedPath === '/v1/blocks';
    for (const user of r.items || []) {
      this.results.append(
        h('div', { class: 'person' },
          h('strong', { text: user.display_name }),
          h('span', { class: 'muted small', text: '@' + user.username }),
          button(blocked ? 'Unblock' : 'View profile', async () => {
            if (!blocked) return this.host.profile(user.username);
            const done = await this.run('DELETE', '/v1/users/' + encode(user.username) + '/block');
            if (done) this.load(true);
          })),
      );
    }
    this.cursor = r.next_cursor ?? null;
    if (reset && !(r.items || []).length) this.results.append(text('No people found.', 'muted'));
  }
}
