export interface IChangelogService {
  getEntries(): ChangelogEntry[]
}

export interface IChangelogRepository {
  getEntries(): ChangelogEntry[]
}

type ChangeType = 'added' | 'changed' | 'fixed'

interface ChangelogItem {
  type: ChangeType
  text: string
}

export interface ChangelogEntry {
  version: string
  date: string
  items: ChangelogItem[]
}

export const tagLabel: Record<ChangeType, string> = {
  added: 'Added',
  changed: 'Changed',
  fixed: 'Fixed'
}
