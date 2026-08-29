import type {
  ITranslationRepository,
  ITranslationService,
  ToolPageData
} from '@/types'

export default class TranslationService implements ITranslationService {
  constructor(private translationRepository: ITranslationRepository) {}

  public getTranslationData(): ToolPageData {
    return this.translationRepository.getTranslationData()
  }
}
