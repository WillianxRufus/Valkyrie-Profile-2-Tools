import type { ToolPageData } from './tool.types'

export interface IVoicesService {
  getVoicesData(): ToolPageData
}

export interface IVoicesRepository {
  getVoicesData(): ToolPageData
}
