import type { ToolPageData } from './tool.types'

export interface ITranslationService {
  getTranslationData(): ToolPageData
}

export interface ITranslationRepository {
  getTranslationData(): ToolPageData
}
