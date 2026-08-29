export interface IAboutService {
  getAboutData(): AboutPageData
}

export interface IAboutRepository {
  getAboutData(): AboutPageData
}

type Stat = {
  label: string
  value: string
}

export type AboutPageData = {
  intro: string
  stats: Stat[]
  repos: { label: string; href: string }[]
}
