import { Suspense, useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { init } from '@/setup'

function RootLayout() {
  useEffect(() => {
    void init()
  }, [])

  return (
    <main>
      <Outlet />
    </main>
  )
}

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="spinner" role="status" aria-label="Loading"></div>
      }
    >
      {children}
    </Suspense>
  )
}

export { LazyPage, RootLayout }
