import type { ToolPageData } from './tool.types'

export interface ICheatsService {
  getCheatsData(): ToolPageData
}

export interface ICheatsRepository {
  getCheatsData(): ToolPageData
}
