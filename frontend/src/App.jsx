import { motion } from 'motion/react'
import { useMemo, useState } from 'react'
import Backdrop from './components/Backdrop'
import LoginScreen from './components/LoginScreen'
import SceneDeck from './components/SceneDeck'
import Ticker from './components/Ticker'
import TopBar from './components/TopBar'
import { useIdleCursor } from './hooks/useIdleCursor'
import { usePulse } from './hooks/usePulse'
import { useSession } from './hooks/useSession'
import { needsAttention, topFor } from './lib/insights'
import { alertScene, ATTENTION_BONUS_SECONDS, isShowable, scenes } from './scenes'

export default function App() {
  useIdleCursor()
  const session = useSession()
  const signedIn = session.status === 'in'
  const { data, offline, clockOffset } = usePulse(signedIn, session.expired)
  const [sceneId, setSceneId] = useState(null)
  const alert = Boolean(data?.health?.alert)

  const playlist = useMemo(() => {
    const base = scenes
      .filter((s) => isShowable(s, data))
      .map((s) => (needsAttention(data, s.id) ? { ...s, seconds: s.seconds + ATTENTION_BONUS_SECONDS } : s))
    return alert ? [alertScene, ...base] : base
  }, [data, alert])

  return (
    <main className="relative isolate flex h-dvh flex-col overflow-hidden">
      <Backdrop alert={alert} />
      <TopBar
        offline={offline || session.status === 'offline'}
        alert={alert}
        insight={data ? topFor(data, sceneId) : null}
        clockOffset={clockOffset}
        username={signedIn ? session.username : null}
        onSignOut={session.signOut}
      />
      {session.status === 'out' ? (
        <LoginScreen onSignIn={session.signIn} />
      ) : data ? (
        <>
          <SceneDeck scenes={playlist} data={data} interrupt={alert} onSceneChange={setSceneId} />
          <Ticker data={data} />
        </>
      ) : (
        <div className="grid flex-1 place-items-center">
          <motion.div
            className="text-[clamp(14px,1.2vw,24px)] text-muted"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            {offline ? 'Waiting for the data service…' : 'Connecting…'}
          </motion.div>
        </div>
      )}
    </main>
  )
}
