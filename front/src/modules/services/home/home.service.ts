import { homeStore } from '@/modules/services/home/home.store'
import type { IHomeService, Image } from '@/types'

export default class HomeService implements IHomeService {
  public getCount(): number {
    return homeStore((state) => state.count)
  }

  public getImages(): Image[] {
    return [
      { src: 'title-cutscene.png', alt: 'Title Cutscene' },
      { src: 'first-cutscene.png', alt: 'First Cutscene' },
      { src: 'world-map.png', alt: 'World Map' },
      { src: 'npc-dialog.png', alt: 'NPC Dialog' },
      { src: 'inn.png', alt: 'Inn' },
      { src: 'menu.png', alt: 'Menu' },
      { src: 'character-background.png', alt: 'Character Background' },
      { src: 'system-message.png', alt: 'System Message' },
      { src: 'final-battle.png', alt: 'Final Battle' },
      { src: 'him.png', alt: 'Him' }
    ]
  }

  public getProjectURL(): string {
    return 'https://github.com/trulio2/Valkyrie-Profile-2-Tools'
  }

  public getImageBase(): string {
    return 'https://raw.githubusercontent.com/trulio2/Valkyrie-Profile-2-Tools/refs/heads/master/images'
  }

  public getDubVideo(): string {
    return 'https://github.com/user-attachments/assets/95875f89-b953-42f8-b083-fad7d9d1d7c8'
  }

  public increment(): void {
    const { count, setCount } = homeStore.getState()

    setCount(count + 1)
  }

  public decrement(): void {
    const { count, setCount } = homeStore.getState()

    setCount(count - 1)
  }

  public reset(): void {
    const { setCount } = homeStore.getState()

    setCount(0)
  }
}
