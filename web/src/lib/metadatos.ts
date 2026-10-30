// Los metadatos del vídeo se escriben aquí pero se pegan en YouTube y TikTok,
// así que lo que importa es en qué forma se copian. Las etiquetas salen del LLM
// como lista y ninguna caja de las redes acepta una lista: la de etiquetas de
// YouTube quiere texto separado por comas, y el título y la descripción quieren
// hashtags. Son las dos formas, no una lista pintada como adornos.

// Una etiqueta como hashtag: sin espacios ni puntuación, porque YouTube corta
// el hashtag en el primer espacio. Las tildes y las eñes se quedan (#sabíasque
// es un hashtag válido). Devuelve "" si no quedaba nada que etiquetar.
export function comoHashtag(etiqueta: string): string {
  const limpio = etiqueta.normalize("NFC").replace(/[^\p{L}\p{N}]+/gu, "");
  return limpio ? `#${limpio}` : "";
}

// Para la caja de etiquetas de YouTube.
export const etiquetasEnLinea = (etiquetas: string[]): string =>
  etiquetas.map((e) => e.trim()).filter(Boolean).join(", ");

// Para pegarlas dentro del título o de la descripción.
export const etiquetasEnHashtags = (etiquetas: string[]): string =>
  etiquetas.map(comoHashtag).filter(Boolean).join(" ");
