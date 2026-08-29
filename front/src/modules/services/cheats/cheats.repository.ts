import type { ICheatsRepository, ToolPageData } from '@/types'

export default class CheatsRepository implements ICheatsRepository {
  public getCheatsData(): ToolPageData {
    return {
      title: 'Cheats Patcher',
      intro: 'Burn cheats directly inside the iso',
      bullets: [
        {
          text: 'Can be used to create a new iso with the Anti-Cheat functions removed from it.'
        }
      ],
      docs: []
    }
  }
}
