import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const api = env.PULSE_API_URL || 'http://127.0.0.1:8000'
  const proxy = Object.fromEntries(['/api', '/manage', '/static'].map((p) => [p, { target: api }]))

  return {
    plugins: [react(), tailwindcss()],
    server: { proxy },
    preview: { proxy },
  }
})
