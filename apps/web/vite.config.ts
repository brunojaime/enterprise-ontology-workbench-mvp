import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit()],
  resolve: {
    conditions: ['browser']
  },
  ssr: {
    noExternal: ['cytoscape']
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts']
  }
});
