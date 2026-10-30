// Profile screen, profile editing and profile photo upload.

import { Page, encode } from '../page.js';
import { button, confirm, h, input, text } from '../ui.js';
import { FeedPage } from './posts.js';
import { PeoplePage } from './people.js';
import { ChatPage } from './chat.js';
import { SettingsPage } from './settings.js';

// Resize to at most 1024px, honour EXIF rotation, re-encode as JPEG under 1 MB.
async function preparePhoto(file) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    throw new Error('unsupported');
  }
  if (!bitmap.width || !bitmap.height || bitmap.width * bitmap.height > 100000000) throw new Error('too large');
  const scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
  if (!blob || blob.size > 1048576) throw new Error('too big');
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export class ProfilePage extends Page {
  constructor(host, username) {
    super(host);
    this.username = username;
    this.header('@' + username, null);
    this.content = this.form();
  }
  async start() {
    super.start();
    const r = await this.run('GET', '/v1/users/' + encode(this.username));
    if (r) {
      this.user = r;
      this.render();
    }
  }
  render() {
    const { host, user, username } = this;
    const photo = h('div', { class: 'photo' });
    this.loadAvatar(username, user.avatar_version, (url) => photo.replaceChildren(h('img', { src: url, alt: '' })));
    const c = this.content;
    c.replaceChildren(
      photo,
      h('h2', { class: 'name', text: user.display_name }),
      text(user.pronouns || '', 'muted small'),
      text(user.bio || ''),
      h('div', { class: 'row' },
        button(user.follower_count + ' followers', () => host.navigate(new PeoplePage(host, '/v1/users/' + encode(username) + '/connections?kind=followers', 'Followers'), 4)),
        button(user.following_count + ' following', () => host.navigate(new PeoplePage(host, '/v1/users/' + encode(username) + '/connections?kind=following', 'Following'), 4))),
    );
    if (user.is_me) {
      const picker = h('input', { type: 'file', accept: 'image/*', hidden: true });
      picker.addEventListener('change', async () => {
        const file = picker.files[0];
        picker.value = '';
        if (!file) return;
        try {
          const encoded = await preparePhoto(file);
          const r = await this.run('PUT', '/v1/me/avatar', { content_base64: encoded });
          if (r) this.start();
        } catch {
          host.info('Photo unavailable', 'Choose a smaller supported image and try again.');
        }
      });
      c.append(
        button('Edit profile', () => this.edit(), 'primary'),
        button('Change profile photo', () => picker.click()),
        picker,
        button('Remove profile photo', async () => {
          if (await this.run('DELETE', '/v1/me/avatar')) this.start();
        }),
        button('Settings', () => host.navigate(new SettingsPage(host), 4)),
      );
    } else {
      c.append(
        button(user.is_following ? 'Following — unfollow' : 'Follow', async () => {
          const r = await this.run(user.is_following ? 'DELETE' : 'PUT', '/v1/users/' + encode(username) + '/follow');
          if (r) { this.user = r; this.render(); }
        }, 'primary'),
        button('Message', async () => {
          const r = await this.run('POST', '/v1/conversations', { username });
          if (r) host.navigate(new ChatPage(host, r.id, username), 3);
        }),
        button('Block this account', async () => {
          if (await confirm('Block @' + username + "? You will stop seeing each other's posts and messages.", 'Block')) {
            if (await this.run('PUT', '/v1/users/' + encode(username) + '/block')) host.home();
          }
        }),
      );
    }
    c.append(button('Posts · ' + user.post_count, () =>
      host.navigate(new FeedPage(host, '/v1/users/' + encode(username) + '/posts', 'Posts by @' + username, false), 4)));
  }
  edit() {
    const { host, user } = this;
    const page = new Page(host);
    page.header('Edit profile', null);
    const f = page.form();
    const name = input('Full name', { value: user.display_name });
    const handle = input('Username', { value: this.username });
    const bio = input('Bio', { multiline: true, value: user.bio || '' });
    const pronouns = input('Pronouns', { value: user.pronouns || '' });
    f.append(name, handle, bio, pronouns, button('Save profile', async () => {
      const r = await page.run('PUT', '/v1/me', {
        username: handle.value, display_name: name.value, bio: bio.value, pronouns: pronouns.value,
      });
      if (r) {
        host.me = { ...r, email_verified: true };
        host.profile(r.username);
      }
    }, 'primary'));
    host.navigate(page, 4);
  }
}
