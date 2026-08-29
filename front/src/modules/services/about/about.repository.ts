import type { AboutPageData, IAboutRepository } from '@/types'

export default class AboutRepository implements IAboutRepository {
  public getAboutData(): AboutPageData {
    return {
      intro: '',
      stats: [],
      repos: [
        {
          label: 'Public (tools + sources)',
          href: 'https://github.com/trulio2/Valkyrie-Profile-2-Tools'
        },
        {
          label: 'Release',
          href: 'https://github.com/trulio2/Valkyrie-Profile-2-Tools/releases'
        }
      ]
    }
  }
}
