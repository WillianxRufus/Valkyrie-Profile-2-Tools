import type { ITranslationRepository, ToolPageData } from '@/types'

export default class TranslationRepository implements ITranslationRepository {
  public getTranslationData(): ToolPageData {
    return {
      title: 'Translation Pipeline',
      intro: '',
      bullets: [],
      docs: [
        {
          label: 'Translating guide',
          href: 'https://github.com/trulio2/Valkyrie-Profile-2-Tools/blob/master/docs/translating.md'
        },
        {
          label: 'Text formats',
          href: 'https://github.com/trulio2/Valkyrie-Profile-2-Tools/blob/master/docs/text-formats.md'
        }
      ]
    }
  }
}
