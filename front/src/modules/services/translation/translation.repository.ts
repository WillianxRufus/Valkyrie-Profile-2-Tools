import type { ITranslationRepository, ToolPageData } from '@/types'

export default class TranslationRepository implements ITranslationRepository {
  public getTranslationData(): ToolPageData {
    return {
      title: 'Translation Pipeline',
      intro: '',
      bullets: [],
      docs: []
    }
  }
}
