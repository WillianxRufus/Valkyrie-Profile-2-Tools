import type { IHomeRepository, Image } from '@/types'

export default class HomeRepository implements IHomeRepository {
  public getDubVideo(): string {
    return 'https://github.com/user-attachments/assets/95875f89-b953-42f8-b083-fad7d9d1d7c8'
  }

  public getImageBase(): string {
    return 'https://raw.githubusercontent.com/trulio2/Valkyrie-Profile-2-Tools/refs/heads/master/images'
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
}
