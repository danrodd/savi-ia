const KINDS: Record<string, string> = {
  xlsx: 'Excel',
  pdf: 'PDF',
  csv: 'CSV',
  docx: 'Word',
}

/** Nombre corto del tipo de archivo, por su extensión. */
export function fileKindLabel(filename: string): string {
  const extension = filename.split('.').pop()?.toLowerCase() ?? ''
  return KINDS[extension] ?? 'Archivo'
}

export function fileSizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}
