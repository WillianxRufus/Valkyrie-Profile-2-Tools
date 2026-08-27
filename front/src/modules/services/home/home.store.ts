import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type HomeState = {
  count: number
  setCount: (value: number) => void
}

export const homeStore = create<HomeState>()(
  persist(
    (set) => ({
      count: 0,
      setCount: (value: number) => set({ count: value })
    }),
    { name: 'home-store' }
  )
)
