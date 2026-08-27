export type Image = {
  src: string
  alt: string
}

export interface IHomeService {
  getImages(): Image[]
  getProjectURL(): string
  getImageBase(): string
  getDubVideo(): string
  getCount(): number
  increment(): void
  decrement(): void
  reset(): void
}
