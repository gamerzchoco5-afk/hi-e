import { defineConfig, loadEnv } from 'vite';

// `npm run dev` serves the app in a desktop browser and forwards /v1 calls to the
// local backend, so you can test without building an APK (no CORS needed).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    root: 'src',
    base: './',
    publicDir: false,
    build: { outDir: '../www', emptyOutDir: true, target: 'es2020' },
    server: {
      port: 5173,
      proxy: { '/v1': env.WIRE_DEV_BACKEND || 'http://127.0.0.1:8000' },
    },
  };
});
