import type {
  ChangelogEntry,
  IChangelogRepository,
  IChangelogService
} from '@/types'

export default class ChangelogService implements IChangelogService {
  constructor(private changelogRepository: IChangelogRepository) {}

  public getEntries(): ChangelogEntry[] {
    return this.changelogRepository.getEntries()
  }
}
