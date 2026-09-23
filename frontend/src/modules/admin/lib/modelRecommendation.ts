import type { LlmProviderKind, ProviderModel } from '../types'

type Scorer = (model: ProviderModel) => number

function modelText(model: ProviderModel): string {
  const metadata = Object.values(model.metadata ?? {})
    .filter((value) => typeof value === 'string' || typeof value === 'number')
    .join(' ')
  return `${model.id} ${model.display_name} ${metadata}`.toLowerCase()
}

/** Penalizaciones comunes a los tres proveedores: nada de esto sirve para chat. */
function excludeNonChat(value: string): number {
  let score = 0
  if (/embedding|embed|vision|image|audio|speech|tts|transcri/.test(value)) score -= 100
  if (/realtime|moderation|dall-e|sora|whisper|codex-mini|computer-use/.test(value)) score -= 100
  if (/preview|experimental|exp|beta/.test(value)) score -= 12
  return score
}

/** Solo toma versiones "chicas" (mayor.minor): un sufijo de fecha tipo
 * `-20251101` no es una versión y no debe dominar el puntaje. */
function versionNumbers(value: string): number[] {
  return (value.match(/(?:\d+\.)?\d+/g) ?? []).map(Number).filter((n) => n < 1000)
}

// Gemini: los alias "-latest" apuntan siempre a la versión vigente y evitan
// que un cliente quede pineado a un modelo que el proveedor da de baja.
const scoreGemini: Scorer = (model) => {
  const value = modelText(model)
  let score = excludeNonChat(value)
  if (/latest/.test(value)) score += 30
  if (/pro|flash/.test(value)) score += 24
  return score
}

// Claude: familias "claude-<línea>-<generación-mayor>[-<menor>][-<fecha>]".
// Solo comparamos la generación mayor (el primer número): un snapshot
// fechado (…-20251101) no debe ganarle a un alias limpio por tener una
// fecha grande, y "4-6" no debe leerse como "6" y ganarle a la generación "5".
const scoreClaude: Scorer = (model) => {
  const value = modelText(model)
  let score = excludeNonChat(value)
  if (/sonnet|opus|haiku/.test(value)) score += 24
  // Sonnet es el default de mejor relación costo/calidad; Opus sigue
  // disponible en la lista, pero no se sugiere primero.
  if (/sonnet/.test(value)) score += 6
  score += (versionNumbers(value)[0] ?? 0) * 2
  return score
}

// OpenAI: familias generalistas `gpt-*`, `chatgpt-*` y los `o*` de
// razonamiento. No fijamos un ID puntual: un modelo nuevo entra sin tocar esto.
//
// Solo el PRIMER número cuenta como generación, igual que en Claude. Los
// IDs de OpenAI arrastran snapshots en formato mes-día (`gpt-4-0613`,
// `gpt-3.5-turbo-instruct-0914`) que son menores a 1000 y se colaban por
// el filtro de fechas: tomando el máximo, `0914` valía 914 y ponía a un
// GPT-3.5 de 2023 como el mejor modelo del catálogo.
//
// La generación pesa más que el alias `-latest`: `-latest` protege contra
// que den de baja un snapshot, pero no vuelve nuevo a un modelo viejo.
const scoreOpenAI: Scorer = (model) => {
  const value = modelText(model)
  let score = excludeNonChat(value)
  if (/(^|[-_/])gpt|chatgpt|(^|[-_/])o\d/.test(value)) score += 24
  if (/latest/.test(value)) score += 5
  score += (versionNumbers(value)[0] ?? 0) * 10
  return score
}

const SCORERS: Record<LlmProviderKind, Scorer> = {
  gemini: scoreGemini,
  claude: scoreClaude,
  openai: scoreOpenAI,
}

export function scoreModel(model: ProviderModel, provider: LlmProviderKind): number {
  return SCORERS[provider](model)
}

export function recommendModel(
  models: ProviderModel[],
  provider: LlmProviderKind,
): ProviderModel | null {
  return [...models].sort((a, b) => scoreModel(b, provider) - scoreModel(a, provider))[0] ?? null
}
