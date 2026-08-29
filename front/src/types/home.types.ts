export type Image = {
  src: string
  alt: string
}

export interface IHomeService {
  getImages(): Image[]
  getProjectURL(): string
  getImageBase(): string
  getDubVideo(): string
}

export interface IHomeRepository {
  getImages(): Image[]
  getProjectURL(): string
  getImageBase(): string
  getDubVideo(): string
}
