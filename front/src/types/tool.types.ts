export type ToolBullet = {
  text: string
}

export type ToolDocLink = {
  label: string
  href: string
}

export type ToolPageData = {
  title: string
  intro: string
  bullets: ToolBullet[]
  docs: ToolDocLink[]
}
