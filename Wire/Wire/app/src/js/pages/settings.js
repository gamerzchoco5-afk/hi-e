// Settings, security and account screens.

import { session } from '../api.js';
import { Page, encode } from '../page.js';
import { button, confirm, formatDateTime, h, info, input, prompt, text } from '../ui.js';
import { FeedPage } from './posts.js';
import { PeoplePage } from './people.js';
import { RecoveryPage } from './auth.js';

export class SettingsPage extends Page {
  constructor(host) {
    super(host);
    this.header('Settings', 'Control what matters.');
    this.content = this.form();
  }
  async start() {
    super.start();
    const s = await this.run('GET', '/v1/settings');
    if (s) this.render(s);
  }
  render(s) {
    const { host } = this;
    const requests = h('input', { type: 'checkbox', id: 'req' });
    requests.checked = !!s.message_requests;
    const activity = h('input', { type: 'checkbox', id: 'act' });
    activity.checked = !!s.show_activity;
    const save = async () => {
      const r = await this.run('PUT', '/v1/settings', { message_requests: requests.checked, show_activity: activity.checked });
      if (r) { requests.checked = !!r.message_requests; activity.checked = !!r.show_activity; }
    };
    requests.addEventListener('change', save);
    activity.addEventListener('change', save);
    const go = (page) => host.navigate(page, 4);
    this.content.replaceChildren(
      h('label', { class: 'switch', for: 'req' }, requests, ' Allow message requests'),
      h('label', { class: 'switch', for: 'act' }, activity, ' Show last activity'),
      text('Email: ' + (s.email_verified ? 'verified' : 'not verified') + '. Verification badges are under construction.', 'small muted'),
      button('Account details', () => host.info('Account', '@' + host.me.username + '\n' + (host.me.email || ''))),
      button('Saved posts', () => go(new FeedPage(host, '/v1/bookmarks', 'Saved posts', false))),
      button('Blocked accounts', () => go(new PeoplePage(host, '/v1/blocks', 'Blocked accounts'))),
      button('Active sessions', () => go(new SessionsPage(host))),
      button('Change password', () => go(new PasswordPage(host, false))),
      button('Create new recovery codes', () => go(new PasswordPage(host, true))),
      button('Privacy', () => go(new PrivacyPage(host))),
      button('Sign out', async () => {
        await this.run('POST', '/v1/auth/logout', {});
        await session.clear();
        host.signIn();
      }, 'primary'),
      button('Sign out of all devices', async () => {
        if (await confirm('Sign out everywhere?', 'Sign out')) {
          await this.run('POST', '/v1/auth/logout-all', {});
          await session.clear();
          host.signIn();
        }
      }),
      button('Delete account', async () => {
        if (!(await confirm('This permanently deletes your account, posts, messages and profile photo.', 'Continue', 'Delete account'))) return;
        const password = await prompt('Confirm password', 'Current password', true);
        if (password === null) return;
        if (await this.run('DELETE', '/v1/me', { password })) {
          await session.clear();
          host.signIn();
        }
      }, 'danger'),
    );
  }
}

class SessionsPage extends Page {
  constructor(host) {
    super(host);
    this.header('Active sessions', 'Devices signed in to your account.');
    this.list = this.form();
  }
  async start() {
    super.start();
    const r = await this.run('GET', '/v1/auth/sessions');
    if (!r) return;
    this.list.replaceChildren();
    for (const s of r.items || []) {
      this.list.append(h('div', { class: 'person' },
        h('strong', { text: s.is_current ? 'This device' : 'Signed-in device' }),
        h('span', { class: 'muted small', text: 'Started ' + formatDateTime(s.created_at) + ' · Expires ' + formatDateTime(s.expires_at) }),
        s.is_current ? null : button('Revoke', async () => {
          if (await this.run('DELETE', '/v1/auth/sessions/' + encode(s.id))) this.start();
        })));
    }
  }
}

class PasswordPage extends Page {
  constructor(host, codesOnly) {
    super(host);
    this.sensitive = true;
    this.header(codesOnly ? 'Create new recovery codes' : 'Change password', 'Confirm it is you.');
    const f = this.form();
    const current = input('Current password', { password: true });
    const next = input('New password (12+ characters)', { password: true });
    next.hidden = codesOnly;
    f.append(current, next, button(codesOnly ? 'Create recovery codes' : 'Change password', async () => {
      if (codesOnly) {
        const r = await this.run('POST', '/v1/auth/recovery-codes', { current_password: current.value });
        if (r) host.navigate(new RecoveryPage(host, r.recovery_codes, () => host.home()), -1);
      } else {
        const r = await this.run('PUT', '/v1/auth/password', { current_password: current.value, new_password: next.value });
        if (r) {
          await session.save(r.token, r.expires_at);
          host.info('Password changed', 'Other devices were signed out.');
          host.home();
        }
      }
    }, 'primary'));
  }
}

class PrivacyPage extends Page {
  constructor(host) {
    super(host);
    this.header('Privacy', 'What Wire stores and shares.');
    this.form().append(
      text('Wire stores your account details, posts, messages, profile photo and sign-in sessions so the service can work.'),
      text('Messages are protected in transit but are not end-to-end encrypted.'),
      text('Linked photos and videos load only when you tap them, directly from the provider, who then sees your IP address.'),
      text('You can export nothing yet; deleting your account removes your data from Wire.', 'muted'),
    );
  }
}
void info;
