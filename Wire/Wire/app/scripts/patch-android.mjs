// Runs after `cap add android`. Copies the small native pieces Wire needs
// (Keystore vault, screenshot guard, icon, backup rules) into the generated project.
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const app = join(root, 'android', 'app', 'src', 'main');
if (!existsSync(app)) {
  console.error('android/ project not found. Run: npx cap add android');
  process.exit(1);
}

const javaDir = join(app, 'java', 'dev', 'wire', 'app');
mkdirSync(javaDir, { recursive: true });
for (const file of ['MainActivity.java', 'WireVaultPlugin.java', 'ScreenGuardPlugin.java']) {
  copyFileSync(join(root, 'native', 'java', file), join(javaDir, file));
}
for (const [from, to] of [
  ['res/xml/data_extraction_rules.xml', 'res/xml/data_extraction_rules.xml'],
  ['res/drawable/ic_app.xml', 'res/drawable/ic_app.xml'],
]) {
  mkdirSync(dirname(join(app, to)), { recursive: true });
  copyFileSync(join(root, 'native', from), join(app, to));
}

const manifestPath = join(app, 'AndroidManifest.xml');
let manifest = readFileSync(manifestPath, 'utf8');
const set = (name, value) => {
  const attr = new RegExp(`\\s${name.replace(':', '\\:')}="[^"]*"`);
  if (attr.test(manifest)) manifest = manifest.replace(attr, ` ${name}="${value}"`);
  else manifest = manifest.replace('<application', `<application ${name}="${value}"`);
};
set('android:allowBackup', 'false');
set('android:fullBackupContent', 'false');
set('android:dataExtractionRules', '@xml/data_extraction_rules');
set('android:icon', '@drawable/ic_app');
manifest = manifest.replace(/\sandroid:roundIcon="[^"]*"/, '');
manifest = manifest.replace(/\sandroid:usesCleartextTraffic="[^"]*"/, '');
if (!/android:screenOrientation=/.test(manifest)) {
  manifest = manifest.replace('<activity', '<activity android:screenOrientation="portrait"');
}
writeFileSync(manifestPath, manifest);
console.log('Android project patched.');
