// App shell: boot, navigation, bottom bar, Android back button and lifecycle.
// Port of MainActivity.java.

import { apiOrigin } from './config.js';
import { cancelAll, clearImages, request, session } from './api.js';
import { exitApp, onActiveChange, onBackButton, setSecureScreen } from './native.js';
import { button, confirm, h, icon, info, text } from './ui.js';
import { Page } from './page.js';
import { AuthPage, RecoveryPage, VerifyPage } from './pages/auth.js';
import { ComposePage, FeedPage } from './pages/posts.js';
import { ChatPage, Inbox } from './pages/chat.js';
import { PeoplePage } from './pages/people.js';
import { ProfilePage } from './pages/profile.js';

const TABS = [
  ['home', 'Home'],
  ['search', 'Search'],
  ['plus', 'Post'],
  ['inbox', 'Inbox'],
  ['me', 'Me'],
];

class Shell {
  constructor() {
    this.me = null;
    this.page = null;
    this.tab = -1;
    this.stage = document.getElementById('stage');
    this.nav = document.getElementById('nav');
    this.navButtons = TABS.map(([name, label], index) => {
      const el = h('button', { type: 'button', class: 'tab', 'aria-label': label, onClick: () => this.tabPressed(index) }, icon(name), h('span', { text: label }));
      this.nav.append(el);
      return el;
    });
  }

  async boot() {
    try {
      apiOrigin();
    } catch (error) {
      this.show(this.message('Server address missing', 'This build has no valid server address. Rebuild with build-apk.bat.'));
      return;
    }
    await session.load();
    onBackButton(() => this.back());
    onActiveChange((on) => {
      if (!this.page) return;
      if (on) this.page.start();
      else {
        this.page.stop();
        cancelAll();
      }
    });
    if (!session.valid()) return this.signIn();
    this.show(this.message('Loading Wire…', ''), -1);
    await this.restore();
  }

  message(title, body) {
    const page = new Page(this);
    page.header(title, null);
    if (body) page.form().append(text(body, 'muted'));
    return page;
  }

  async restore() {
    try {
      this.me = await request(this, 'GET', '/v1/me');
      const codes = await session.pendingRecovery();
      if (codes) this.navigate(new RecoveryPage(this, codes, () => this.afterRecovery()), -1);
      else this.afterRecovery();
    } catch (error) {
      if (error.status === 401) return this.signIn();
      const page = this.message('Cannot reach Wire', error.message);
      const f = page.form();
      f.append(
        button('Try again', () => this.restore(), 'primary'),
        button('Sign out on this device', async () => { await session.clear(); this.signIn(); }),
      );
      this.show(page, -1);
    }
  }

  afterRecovery() {
    if (!this.me.email_verified) this.navigate(new VerifyPage(this), -1);
    else this.home();
  }

  async signedIn(r) {
    await session.save(r.token, r.expires_at);
    this.me = r.user;
    const next = () => this.afterRecovery();
    if (r.recovery_codes) this.navigate(new RecoveryPage(this, r.recovery_codes, next), -1);
    else next();
  }

  signIn() {
    cancelAll();
    clearImages();
    this.me = null;
    this.navigate(new AuthPage(this, 0), -1);
  }

  home() {
    this.navigate(new FeedPage(this, '/v1/feed?mode=discover', 'Fresh from the people you care about', true), 0);
  }

  profile(username) {
    this.navigate(new ProfilePage(this, username), username === this.me?.username ? 4 : -1);
  }

  info(title, message) {
    info(title, message);
  }

  error(error) {
    const wait = error.status === 429 || error.status === 423;
    info(wait ? 'Please wait' : 'Something needs attention', error.message + (wait ? '\nRequests are paused on this device.' : ''));
  }

  tabPressed(index) {
    if (!this.me?.email_verified) return;
    if (index === 0) this.home();
    else if (index === 1) this.navigate(new PeoplePage(this), 1);
    else if (index === 2) this.navigate(new ComposePage(this), 2);
    else if (index === 3) this.navigate(new Inbox(this), 3);
    else this.profile(this.me.username);
  }

  navigate(page, tab = -1) {
    if (this.page) this.page.dispose();
    this.show(page, tab);
  }

  show(page, tab = -1) {
    this.page = page;
    this.tab = tab;
    this.stage.replaceChildren(page.view());
    setSecureScreen(!!page.sensitive);
    const showNav = tab >= 0 && !(page instanceof ChatPage);
    this.nav.hidden = !showNav;
    this.navButtons.forEach((el, i) => el.classList.toggle('on', i === tab));
    page.start();
  }

  async back() {
    const page = this.page;
    if (document.querySelector('.overlay')) {
      document.querySelector('.overlay:last-child')?.remove();
    } else if (page?.isRecovery) {
      info('Save your codes', 'Copy your recovery codes and tap "I saved my codes" to continue.');
    } else if (page instanceof ChatPage) this.navigate(new Inbox(this), 3);
    else if (this.me?.email_verified) {
      if (page instanceof FeedPage && page.homeFeed) {
        if (await confirm('Close Wire?', 'Close')) exitApp();
      } else this.home();
    } else if (page instanceof AuthPage && page.mode !== 0) this.navigate(new AuthPage(this, 0), -1);
    else exitApp();
  }
}

new Shell().boot();
