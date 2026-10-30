// Sign in, sign up, password recovery, email verification and recovery-code screens.

import { session } from '../api.js';
import { copySensitive } from '../native.js';
import { Page, encode } from '../page.js';
import { button, h, info, input, text } from '../ui.js';

export class AuthPage extends Page {
  constructor(host, mode = 0) {
    super(host);
    this.mode = mode;
    this.sensitive = true;
    this.header(
      mode === 1 ? 'Make it yours.' : mode === 2 ? 'Get back in.' : 'Welcome to Wire.',
      mode === 1
        ? 'Your words. Your people.'
        : mode === 2
          ? 'Use one of your saved recovery codes.'
          : 'A little less noise. A little more you.',
    );
    const f = this.form();
    const identity = input(mode === 1 ? 'Username' : 'Email or username');
    f.append(identity);
    const name = input('Full name');
    const email = input('Email address', { type: 'email' });
    const password = input(
      mode === 2 ? 'New password (12+ characters)' : 'Password (12+ characters for signup)',
      { password: true },
    );
    const recovery = input('Single-use recovery code', { password: true });
    const birthday = input('Date of birth', { type: 'date' });
    birthday.max = new Date().toISOString().slice(0, 10);

    if (mode === 1) {
      f.append(
        button('Check username', async () => {
          const username = identity.value.trim().toLowerCase();
          const r = await this.run('GET', '/v1/auth/username?username=' + encode(username));
          if (r) {
            host.info(
              'Username',
              r.available
                ? '@' + username + ' is available. It is reserved when signup finishes.'
                : 'Choose another username.',
            );
          }
        }),
        name,
        email,
        h('label', { class: 'field-label', text: 'Date of birth' }),
        birthday,
      );
    }
    if (mode === 2) f.append(recovery);
    f.append(password);

    const submit = button(
      mode === 1 ? 'Create account' : mode === 2 ? 'Reset password & sign in' : 'Sign in',
      async () => {
        const body = { username: identity.value.trim().toLowerCase() };
        if (mode === 2) {
          body.code = recovery.value.trim();
          body.new_password = password.value;
        } else body.password = password.value;
        if (mode === 1) {
          body.display_name = name.value;
          body.email = email.value;
          body.date_of_birth = birthday.value;
        }
        submit.disabled = true;
        const r = await this.run(
          'POST',
          mode === 1 ? '/v1/auth/register' : mode === 2 ? '/v1/auth/recover' : '/v1/auth/login',
          body,
        );
        if (r) await host.signedIn(r);
        else submit.disabled = false;
      },
      'primary',
    );
    f.append(submit);
    if (mode !== 1) f.append(button('Create an account', () => host.navigate(new AuthPage(host, 1), -1)));
    if (mode !== 0) f.append(button('Already have an account? Sign in', () => host.navigate(new AuthPage(host, 0), -1)));
    if (mode === 0) f.append(button('Forgot password?', () => host.navigate(new AuthPage(host, 2), -1)));
    f.append(
      text(
        'Keep your recovery codes somewhere safe. Each code can reset your password once. Wire requires age 13 or older.',
        'small muted',
      ),
    );
  }

  start() {
    super.start();
    for (const b of this.root.querySelectorAll('button')) b.disabled = false;
  }
}

export class VerifyPage extends Page {
  constructor(host) {
    super(host);
    this.sensitive = true;
    this.header('Check your inbox.', 'Verify your email before posting or chatting.');
    const f = this.form();
    f.append(
      text('Request an email code, then enter the 8 digits below. Codes expire after 10 minutes.', 'muted'),
      button(
        'Send verification email',
        async () => {
          const r = await this.run('POST', '/v1/auth/email/send', {});
          if (r) host.info('Email sent', 'Check your inbox and spam folder.');
        },
        'primary',
      ),
    );
    const code = input('8-digit code');
    code.inputMode = 'numeric';
    code.maxLength = 8;
    f.append(
      code,
      button(
        'Verify email',
        async () => {
          const r = await this.run('POST', '/v1/auth/email/verify', { code: code.value });
          if (r) {
            host.me.email_verified = true;
            host.home();
          }
        },
        'primary',
      ),
      button('Sign out on this device', async () => {
        await session.clear();
        host.signIn();
      }),
    );
  }
}

export class RecoveryPage extends Page {
  constructor(host, codes, next) {
    super(host);
    this.sensitive = true;
    this.isRecovery = true;
    session.savePendingRecovery(codes).catch(() => {
      host.info('Secure storage unavailable', 'Save these codes before leaving this screen.');
    });
    this.header('Save these codes.', 'They are shown once. Each code works once.');
    const f = this.form();
    const content = codes.join('\n');
    f.append(
      h('pre', { class: 'codes', text: content }),
      text(
        'Anyone with one of these codes can reset your password. Keep them in a trusted password manager or somewhere private.',
        'muted',
      ),
      button('Copy recovery codes', async () => {
        await copySensitive(content);
        host.info('Copied', 'Clipboard copy will be cleared after a minute. Save your codes privately.');
      }),
      button(
        'I saved my codes — continue',
        async () => {
          await session.clearPendingRecovery();
          next();
        },
        'primary',
      ),
    );
  }
}
