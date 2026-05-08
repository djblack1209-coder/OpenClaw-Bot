const HTML_ENTITY_MAP: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
};

function decodeCodePoint(codePoint: number, fallback: string): string {
  if (!Number.isInteger(codePoint) || codePoint < 0 || codePoint > 0x10ffff) {
    return fallback;
  }
  return String.fromCodePoint(codePoint);
}

/** 解码常见 HTML 实体，避免用 innerHTML 处理外部文本。 */
export function decodeHtmlEntities(value: string): string {
  if (!value || !value.includes('&')) return value;
  return value.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z][a-zA-Z0-9]+);/g, (match, entity: string) => {
    if (entity.startsWith('#x') || entity.startsWith('#X')) {
      const codePoint = Number.parseInt(entity.slice(2), 16);
      return decodeCodePoint(codePoint, match);
    }
    if (entity.startsWith('#')) {
      const codePoint = Number.parseInt(entity.slice(1), 10);
      return decodeCodePoint(codePoint, match);
    }
    return HTML_ENTITY_MAP[entity] ?? match;
  });
}
