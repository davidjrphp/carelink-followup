/// <reference types="vitest" />
import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  build: {
    // Clinic PCs run older browsers; keep output syntax conservative.
    target: ['es2019', 'chrome80', 'firefox78', 'safari13', 'edge80'],
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        // Measurement harness for the 10,000-row before/after numbers (fixture data only).
        bench: resolve(__dirname, 'bench.html'),
      },
    },
  },
  server: {
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
