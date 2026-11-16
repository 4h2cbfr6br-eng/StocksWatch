// The "turn on notifications" strip. It registers this phone or browser with
// the database, so the scanner knows where to send alerts.
import { useEffect, useState } from 'react'
import { supabase } from './supabase'

type State = 'checking' | 'unsupported' | 'needs-install' | 'off' | 'on' | 'blocked' | 'working'

function keyBytes(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(base64url.length / 4) * 4, '=')
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))
}

const isIphone = /iPhone|iPad|iPod/.test(navigator.userAgent)
const installed =
  window.matchMedia('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true

export default function Notify() {
  const [state, setState] = useState<State>('checking')
  const [problem, setProblem] = useState('')

  useEffect(() => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
      // On an iPhone, notifications only exist once the app is on the Home Screen.
      setState(isIphone && !installed ? 'needs-install' : 'unsupported')
      return
    }
    if (Notification.permission === 'denied') return setState('blocked')
    navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => setState(subscription ? 'on' : 'off'))
      .catch(() => setState('off'))
  }, [])

  async function turnOn() {
    setState('working')
    setProblem('')
    try {
      if ((await Notification.requestPermission()) !== 'granted') return setState('blocked')
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(__VAPID_PUBLIC_KEY__).buffer as ArrayBuffer,
      })
      const json = subscription.toJSON()
      const { error } = await supabase
        .from('push_subscriptions')
        .upsert({ endpoint: json.endpoint, keys: json.keys }, { onConflict: 'endpoint' })
      if (error) throw new Error(error.message)
      setState('on')
    } catch (error) {
      setProblem((error as Error).message)
      setState('off')
    }
  }

  async function turnOff() {
    setState('working')
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    if (subscription) {
      await supabase.from('push_subscriptions').delete().eq('endpoint', subscription.endpoint)
      await subscription.unsubscribe()
    }
    setState('off')
  }

  if (state === 'checking' || state === 'unsupported') return null
  return (
    <div className="notify">
      <div className="wrap notify-row">
        {state === 'needs-install' && (
          <span>
            To get alerts on this iPhone: tap the Share button, choose <b>Add to Home Screen</b>, then open
            StocksWatch from the new icon.
          </span>
        )}
        {state === 'blocked' && (
          <span>Notifications are blocked for StocksWatch on this device. Allow them in Settings to get alerts.</span>
        )}
        {(state === 'off' || state === 'working') && (
          <>
            <span>Get a notification when a large stock, or one on your watchlist, falls sharply.</span>
            <button onClick={turnOn} disabled={state === 'working'}>
              {state === 'working' ? 'Working…' : 'Turn on notifications'}
            </button>
          </>
        )}
        {state === 'on' && (
          <>
            <span className="muted">Notifications are on for this device.</span>
            <button className="link-button" onClick={turnOff}>Turn off</button>
          </>
        )}
        {problem && <span className="error">Could not turn on: {problem}</span>}
      </div>
    </div>
  )
}
