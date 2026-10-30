// Tap-to-load linked media. Port of MediaPreview.java: only YouTube and a short list
// of image/video hosts are accepted, nothing loads until the reader taps, and only
// one preview is active at a time.

import { h, button } from './ui.js';
import { openExternal } from './native.js';

const TRUSTED = new Set([
  'i.imgur.com',
  'images.unsplash.com',
  'images.pexels.com',
  'videos.pexels.com',
  'upload.wikimedia.org',
]);

let current = null;

function parseMedia(body) {
  for (const match of body.matchAll(/https:\/\/[^\s<>]+/gi)) {
    const url = match[0].replace(/[),.!?]+$/, '');
    let u;
    try {
      u = new URL(url);
    } catch {
      continue;
    }
    if (u.username || u.password || u.port) continue;
    const domain = u.hostname.toLowerCase();
    let id = null;
    if (domain === 'youtu.be') id = u.pathname.split('/').filter(Boolean).pop() || null;
    else if (['youtube.com', 'www.youtube.com', 'm.youtube.com'].includes(domain)) {
      id = u.searchParams.get('v');
      if (!id && (u.pathname.startsWith('/shorts/') || u.pathname.startsWith('/embed/'))) {
        id = u.pathname.split('/').filter(Boolean).pop() || null;
      }
    }
    if (id && /^[A-Za-z0-9_-]{11}$/.test(id)) return { url, youtubeId: id, kind: 'video' };
    if (!TRUSTED.has(domain)) continue;
    const path = u.pathname.toLowerCase();
    if (path.endsWith('.mp4') || path.endsWith('.webm')) return { url, youtubeId: null, kind: 'video' };
    if (
      /\.(jpe?g|png|webp)$/.test(path) ||
      domain === 'images.unsplash.com' ||
      domain === 'images.pexels.com'
    ) {
      return { url, youtubeId: null, kind: 'photo' };
    }
  }
  return null;
}

export function stopAllMedia() {
  const previous = current;
  current = null;
  if (previous) previous.release();
}

// Returns an element, or null when the text has no supported link.
export function createMedia(body) {
  const spec = parseMedia(body);
  if (!spec) return null;
  const box = h('div', { class: 'media' });

  const showPrompt = () => {
    box.replaceChildren(button('Tap to load linked ' + spec.kind, load));
  };

  const load = () => {
    stopAllMedia();
    current = { release: showPrompt };
    const children = [
      h('p', { class: 'txt tiny muted', text: "Loaded from the link's provider. They receive your IP address." }),
    ];
    if (spec.youtubeId) {
      children.push(
        h('iframe', {
          class: 'media-frame',
          src: 'https://www.youtube-nocookie.com/embed/' + spec.youtubeId,
          allow: 'encrypted-media; fullscreen',
          referrerpolicy: 'strict-origin-when-cross-origin',
          sandbox: 'allow-scripts allow-same-origin allow-presentation',
          allowfullscreen: true,
          title: 'Linked video',
        }),
      );
    } else if (spec.kind === 'video') {
      children.push(
        h('video', {
          class: 'media-frame',
          src: spec.url,
          controls: true,
          playsinline: true,
          preload: 'metadata',
          referrerpolicy: 'no-referrer',
        }),
      );
    } else {
      children.push(
        h('img', {
          class: 'media-image',
          src: spec.url,
          alt: 'Linked photo',
          referrerpolicy: 'no-referrer',
          decoding: 'async',
        }),
      );
    }
    children.push(button('Open original link', () => openExternal(spec.url)));
    box.replaceChildren(...children);
  };

  showPrompt();
  return box;
}
