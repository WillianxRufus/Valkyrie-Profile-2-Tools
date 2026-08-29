import type { ChangelogEntry, IChangelogRepository } from '@/types'

export default class ChangelogRepository implements IChangelogRepository {
  public getEntries(): ChangelogEntry[] {
    return [
      {
        version: 'v0.0.3',
        date: '2026-08-28',
        items: []
      }
    ]
  }
}
