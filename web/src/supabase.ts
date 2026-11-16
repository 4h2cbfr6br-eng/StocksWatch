import { createClient } from '@supabase/supabase-js'

// Design preview: only on the local dev server, and only when asked for.
export const PREVIEW =
  import.meta.env.DEV && new URLSearchParams(window.location.search).has('preview')

export const supabase = PREVIEW
  ? createClient(`${window.location.origin}/__dev`, 'preview', {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    })
  : createClient(__SUPABASE_URL__, __SUPABASE_PUBLISHABLE_KEY__)
