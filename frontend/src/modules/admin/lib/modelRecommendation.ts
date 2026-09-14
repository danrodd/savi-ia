import type { ProviderModel } from '../types'

export function scoreModel(model: ProviderModel): number {
  const metadata = Object.values(model.metadata ?? {})
    .filter((value) => typeof value === 'string' || typeof value === 'number')
    .join(' ')
  const value = `${model.id} ${model.display_name} ${metadata}`.toLowerCase()
  let score = 0

  if (/embedding|embed|vision|image|audio|speech|tts|transcri/.test(value)) score -= 100
  if (/preview|experimental|exp|beta|latest/.test(value)) score -= 12
  if (/chat|sonnet|opus|gemini|pro|flash|general|text/.test(value)) score += 24

  const versions = value.match(/(?:\d+\.)?\d+/g)?.map(Number) ?? []
  return score + Math.max(...versions, 0) * 2
}

export function recommendModel(models: ProviderModel[]): ProviderModel | null {
  return [...models].sort((a, b) => scoreModel(b) - scoreModel(a))[0] ?? null
}
