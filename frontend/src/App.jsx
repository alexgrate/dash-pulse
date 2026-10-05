import { motion } from 'motion/react'
import { useMemo, useState } from 'react'
import Backdrop from './components/Backdrop'
import ExplorePanel from './components/ExplorePanel'
import LoginScreen from './components/LoginScreen'
import SceneDeck from './components/SceneDeck'
import SetPasswordScreen, { readSetupLink } from './components/SetPasswordScreen'
import Ticker from './components/Ticker'
import TopBar from './components/TopBar'
import { useIdleCursor } from './hooks/useIdleCursor'
import { usePulse } from './hooks/usePulse'
import { useSession } from './hooks/useSession'
import { ExploreContext } from './lib/explore'
import { needsAttention, topFor } from './lib/insights'
import { alertScene, ATTENTION_BONUS_SECONDS, isShowable, scenes } from './scenes'

export default function App() {
  const session = useSession()
  const signedIn = session.status === 'in'
  const [setupLink, setSetupLink] = useState(readSetupLink)
  const [notice, setNotice] = useState('')
  const [exploreOn, setExploreOn] = useState(false)
  const [stack, setStack] = useState([])
  const exploring = signedIn && session.canExplore && exploreOn
  useIdleCursor(!exploring)
  const explore = useMemo(() => ({ enabled: exploring, open: (to) => setStack([to]) }), [exploring])
  const { data, offline, clockOffset } = usePulse(signedIn, session.expired)
  const [sceneId, setSceneId] = useState(null)
  const alert = Boolean(data?.health?.alert)

  async function finishSetup(message) {
    window.history.replaceState(null, '', window.location.pathname)
    setSetupLink(null)
    setNotice(message)
    if (message && signedIn) await session.signOut()
  }

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
        isAdmin={signedIn && session.isAdmin}
        canExplore={signedIn && session.canExplore}
        exploring={exploring}
        onToggleExplore={() => {
          setExploreOn((v) => !v)
          setStack([])
        }}
        onSignOut={session.signOut}
      />
      {setupLink ? (
        <SetPasswordScreen link={setupLink} onDone={finishSetup} />
      ) : session.status === 'out' ? (
        <LoginScreen onSignIn={session.signIn} notice={notice} />
      ) : data ? (
        <>
          <ExploreContext.Provider value={explore}>
            <SceneDeck scenes={playlist} data={data} interrupt={alert} frozen={exploring} onSceneChange={setSceneId} />
          </ExploreContext.Provider>
          <Ticker data={data} />
          {exploring && <ExplorePanel stack={stack} setStack={setStack} />}
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
