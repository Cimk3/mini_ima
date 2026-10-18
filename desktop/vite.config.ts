import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    watch: { ignored: ['**/.venv/**', '**/src-tauri/**', '**/build/**', '**/dist/**'] },
  },
  build: { outDir: 'build/frontend', emptyOutDir: true },
  test: { include: ['src/test/**/*.test.{ts,tsx}'], environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], restoreMocks: true },
});
