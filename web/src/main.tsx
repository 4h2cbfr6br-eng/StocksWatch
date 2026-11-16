import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/playfair-display/700.css'
import '@fontsource/playfair-display/900.css'
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/hanken-grotesk/wght.css'
import './styles.css'
import App from './App'

// The service worker is what lets a notification arrive when the app is closed.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {})
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
