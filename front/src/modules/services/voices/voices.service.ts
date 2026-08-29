import type { IVoicesRepository, IVoicesService, ToolPageData } from '@/types'

export default class VoicesService implements IVoicesService {
  constructor(private voicesRepository: IVoicesRepository) {}

  public getVoicesData(): ToolPageData {
    return this.voicesRepository.getVoicesData()
  }
}
