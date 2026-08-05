import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Deploy owns `base` and the /api proxy. Changing them here breaks the deployed
// app while dev keeps working — the worst kind of change to make.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
