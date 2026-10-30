// Feed, thread and compose screens plus the post card.

import { Page } from '../page.js';
import { actionButton, button, choose, confirm, h, info, input, linkify, prompt } from '../ui.js';
import { createMedia, stopAllMedia } from '../media.js';
import { shareText } from '../native.js';
import { PeoplePage } from './people.js';

void PeoplePage;

function postCard(page, post, detail, onChange, onRemove) {
  const host = page.host;
  const author = post.author;
  if (!author) return null;
  const letter = h('div', { class: 'avatar' }, (author.display_name || '?').slice(0, 1));
  const top = h(
    'div',
    { class: 'row post-top', onClick: () => host.profile(author.username) },
    letter,
    h('div', { class: 'grow who' }, h('strong', { text: author.display_name }), h('span', { class: 'muted small', text: '@' + author.username })),
  );
  page.loadAvatar(author.username, author.avatar_version, (url) => letter.replaceChildren(h('img', { src: url, alt: '' })));

  const body = h('p', { class: 'post-body' + (detail ? ' selectable' : ' clamp') }, linkify(post.body || ''));
  const card = h('article', { class: 'post' }, top);
  if (post.title) card.append(h('h2', { class: 'post-title', text: post.title }));
  card.append(body);
  if (!detail) {
    card.append(h('a', { href: '#', class: 'link open', text: 'View thread →', onClick: (e) => { e.preventDefault(); host.navigate(new ThreadPage(host, post.id), 0); } }));
  }
  const media = createMedia(post.body || '');
  if (media) card.append(media);

  const mutate = async (method, action) => {
    const value = await page.run(method, '/v1/posts/' + post.id + '/' + action);
    if (value) onChange(post, value);
  };
  card.append(
    h(
      'div',
      { class: 'row actions' },
      actionButton((post.liked ? '♥ ' : '♡ ') + (post.like_count || 0), () => mutate(post.liked ? 'DELETE' : 'PUT', 'like')),
      actionButton('Reply ' + (post.reply_count || 0), () =>
        host.navigate(new ComposePage(host, post.parent_id > 0 ? post.parent_id : post.id), 2),
      ),
      actionButton(post.bookmarked ? 'Saved' : 'Save', () => mutate(post.bookmarked ? 'DELETE' : 'PUT', 'bookmark')),
    ),
    h('button', {
      type: 'button',
      class: 'act more',
      'aria-label': 'Post options',
      text: '•••',
      onClick: async () => {
        const options = author.is_me ? ['Share text', 'Delete post'] : ['Share text', 'Report post'];
        const index = await choose(options);
        if (index === 0) shareText(post.body || '');
        else if (index === 1 && author.is_me) {
          if (await confirm('Delete this post and its replies?', 'Delete')) {
            const r = await page.run('DELETE', '/v1/posts/' + post.id);
            if (r) onRemove(post);
          }
        } else if (index === 1) {
          const reason = await prompt('Report post', 'What happened?');
          if (reason !== null) {
            const r = await page.run('PUT', '/v1/posts/' + post.id + '/report', { reason });
            if (r) info('Report submitted', 'Your report has been recorded.');
          }
        }
      },
    }),
  );
  return card;
}

class PostList {
  constructor(page, detail) {
    this.page = page;
    this.detail = detail;
    this.items = [];
    this.el = h('div', { class: 'scroll list' });
  }
  render() {
    stopAllMedia();
    const cards = this.items.map((post) =>
      postCard(
        this.page,
        post,
        this.detail,
        (old, value) => {
          const at = this.items.indexOf(old);
          if (at >= 0) this.items[at] = value;
          this.render();
        },
        (old) => {
          this.items = this.items.filter((p) => p !== old);
          this.render();
        },
      ),
    );
    this.el.replaceChildren(...cards.filter(Boolean));
  }
}

export class FeedPage extends Page {
  constructor(host, path, title, tabs) {
    super(host);
    this.path = path;
    this.homeFeed = tabs;
    this.cursor = null;
    this.loading = false;
    this.header('Wire', title);
    if (tabs) {
      this.root.append(
        h(
          'div',
          { class: 'row pad tabs' },
          button('For you', () => { this.path = '/v1/feed?mode=discover'; this.load(true); }),
          button('Following', () => { this.path = '/v1/feed?mode=following'; this.load(true); }),
        ),
      );
    }
    this.list = new PostList(this, false);
    this.root.append(this.list.el);
    this.more = button('Load more', () => this.load(false));
    this.root.append(h('div', { class: 'row pad footer' }, button('Refresh', () => this.load(true)), this.more));
  }
  start() {
    super.start();
    this.loading = false;
    this.load(true);
  }
  stop() {
    stopAllMedia();
    super.stop();
  }
  async load(reset) {
    if (this.loading) return;
    if (!reset && this.cursor === null) return;
    this.loading = true;
    this.more.disabled = true;
    const url = this.path + (this.path.includes('?') ? '&' : '?') + 'limit=15' + (!reset && this.cursor !== null ? '&cursor=' + this.cursor : '');
    const r = await this.run('GET', url);
    this.loading = false;
    if (!r) {
      this.more.disabled = false;
      return;
    }
    if (reset) this.list.items = [];
    this.list.items.push(...(r.items || []));
    this.cursor = r.next_cursor ?? null;
    this.list.render();
    this.more.disabled = this.cursor === null;
    if (!this.list.items.length) this.host.info('Nothing here yet', 'Follow people or publish your first post.');
  }
}

export class ThreadPage extends Page {
  constructor(host, id) {
    super(host);
    this.id = id;
    this.cursor = null;
    this.header('Thread', null);
    this.list = new PostList(this, true);
    this.root.append(this.list.el);
    this.root.append(
      h('div', { class: 'row pad footer' },
        button('Reply', () => host.navigate(new ComposePage(host, id), 2), 'primary'),
        button('More replies', () => this.replies(false))),
    );
  }
  async start() {
    super.start();
    this.list.items = [];
    const post = await this.run('GET', '/v1/posts/' + this.id);
    if (!post) return;
    this.list.items.push(post);
    this.list.render();
    this.replies(true);
  }
  stop() {
    stopAllMedia();
    super.stop();
  }
  async replies(first) {
    if (!first && this.cursor === null) return;
    const r = await this.run('GET', '/v1/posts/' + this.id + '/replies?limit=20' + (!first ? '&cursor=' + this.cursor : ''));
    if (!r) return;
    this.list.items.push(...(r.items || []));
    this.cursor = r.next_cursor ?? null;
    this.list.render();
  }
}

export class ComposePage extends Page {
  constructor(host, parent = null) {
    super(host);
    this.header(parent === null ? 'Say something.' : 'Join the thread.', parent === null ? 'A thought, a story, a different point of view.' : 'Keep the conversation going.');
    const f = this.form();
    const article = h('input', { type: 'checkbox', id: 'article' });
    const toggle = h('label', { class: 'switch', for: 'article' }, article, ' Long article');
    toggle.hidden = parent !== null;
    const title = input('Article title');
    title.hidden = true;
    article.addEventListener('change', () => (title.hidden = !article.checked));
    const body = input("What's on your mind?", { multiline: true });
    body.rows = 8;
    const clientId = crypto.randomUUID();
    const send = button(parent === null ? 'Publish' : 'Post reply', async () => {
      const payload = {
        body: body.value,
        title: article.checked ? title.value : '',
        kind: article.checked ? 'article' : 'note',
        client_id: clientId,
      };
      if (parent !== null) payload.parent_id = parent;
      send.disabled = true;
      const r = await this.run('POST', '/v1/posts', payload);
      if (r) host.navigate(new ThreadPage(host, parent === null ? r.id : parent), 0);
      else send.disabled = false;
    }, 'primary');
    f.append(toggle, title, body,
      h('p', { class: 'txt small muted', text: 'Notes: 500 characters · Articles: 10,000. Paste a link to share it. Supported linked media can be loaded by the reader.' }),
      send, button('Cancel', () => host.home()));
  }
}
