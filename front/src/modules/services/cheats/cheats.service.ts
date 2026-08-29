import type { ICheatsRepository, ICheatsService, ToolPageData } from '@/types'

export default class CheatsService implements ICheatsService {
  constructor(private cheatsRepository: ICheatsRepository) {}

  public getCheatsData(): ToolPageData {
    return this.cheatsRepository.getCheatsData()
  }
}
