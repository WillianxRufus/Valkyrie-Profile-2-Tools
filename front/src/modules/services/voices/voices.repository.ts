import type { ToolPageData } from '@/types'

import type { IVoicesRepository } from '@/types'

export default class VoicesRepository implements IVoicesRepository {
  public getVoicesData(): ToolPageData {
    return {
      title: 'Voices Tool',
      intro: '',
      bullets: [],
      docs: []
    }
  }
}
