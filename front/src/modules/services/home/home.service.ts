import type { IHomeRepository, IHomeService, Image } from '@/types'

export default class HomeService implements IHomeService {
  constructor(private homeRepository: IHomeRepository) {}

  public getDubVideo(): string {
    return this.homeRepository.getDubVideo()
  }

  public getImageBase(): string {
    return this.homeRepository.getImageBase()
  }

  public getImages(): Image[] {
    return this.homeRepository.getImages()
  }

  public getProjectURL(): string {
    return this.homeRepository.getProjectURL()
  }
}
