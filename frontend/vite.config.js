import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  return {
    server: {
      port: 3000,
      open: true,
    },
    // So code using process.env.NEXT_PUBLIC_* (e.g. Flux Supabase client) works in Vite.
    define: {
      'process.env': {
        NEXT_PUBLIC_SUPABASE_URL: env.NEXT_PUBLIC_SUPABASE_URL || '',
        NEXT_PUBLIC_SUPABASE_ANON_KEY: env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '',
        ORCHESTRATOR_URL: env.ORCHESTRATOR_URL || 'http://localhost:8000'
      }
    },
  }
})
