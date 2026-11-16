import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The keys live in the project's .env file, one folder up.
// Only the URL, the PUBLISHABLE key and the PUBLIC notification key are built into the web app.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', ['SUPABASE_', 'VAPID_PUBLIC_'])
  const secret = env.SUPABASE_SECRET_KEY

  return {
    // On the public site the app lives in a sub-folder (set by the deploy job).
    base: process.env.BASE_PATH || '/',
    plugins: [react()],
    define: {
      __SUPABASE_URL__: JSON.stringify(env.SUPABASE_URL ?? ''),
      __SUPABASE_PUBLISHABLE_KEY__: JSON.stringify(env.SUPABASE_PUBLISHABLE_KEY ?? ''),
      // The PUBLIC half of the notification key pair. The private half never comes here.
      __VAPID_PUBLIC_KEY__: JSON.stringify(env.VAPID_PUBLIC_KEY ?? ''),
    },
    server: {
      port: 5173,
      strictPort: true,
      // Design preview (add ?preview=1 to the address): lets the page read the
      // database without signing in. Works only on this Mac's dev server, is
      // read-only, and the secret key stays inside this process.
      proxy: secret
        ? {
            '/__dev': {
              target: env.SUPABASE_URL,
              changeOrigin: true,
              rewrite: (path) => path.replace(/^\/__dev/, ''),
              headers: { apikey: secret, authorization: `Bearer ${secret}` },
              bypass: (req) => (req.method === 'GET' ? undefined : false),
              // Supabase refuses the secret key on requests that look like they
              // come from a browser, so send them on as a plain server request.
              configure: (proxy) => {
                proxy.on('proxyReq', (proxyReq) => {
                  proxyReq.setHeader('user-agent', 'stockswatch-dev-preview')
                  for (const name of proxyReq.getHeaderNames()) {
                    if (name === 'origin' || name === 'referer' || name === 'cookie' || name.startsWith('sec-')) {
                      proxyReq.removeHeader(name)
                    }
                  }
                })
              },
            },
          }
        : undefined,
    },
  }
})
