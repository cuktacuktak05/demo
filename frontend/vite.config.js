import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      // Proxy API requests to the FastAPI backend
      '/ask': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/audit': 'http://127.0.0.1:8000',
      '/mask-test': 'http://127.0.0.1:8000',
      '/demask-test': 'http://127.0.0.1:8000',
      '/check-role': 'http://127.0.0.1:8000',
      '/check-prompt-safety': 'http://127.0.0.1:8000',
      '/check-output': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
      '/docs': 'http://127.0.0.1:8000',
      '/openapi.json': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
});

