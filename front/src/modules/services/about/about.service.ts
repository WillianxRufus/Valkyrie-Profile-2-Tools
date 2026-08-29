import type { AboutPageData, IAboutRepository, IAboutService } from '@/types'

export default class AboutService implements IAboutService {
  constructor(private aboutRepository: IAboutRepository) {}

  public getAboutData(): AboutPageData {
    return this.aboutRepository.getAboutData()
  }
}
