// Escapado para HTML que se construye como cadena (el visor lo inserta con
// {@html}). Los títulos vienen del LLM o del usuario: una comilla o un `<` sin
// escapar rompe el atributo y, peor, permite colar marcado.
const ENTIDADES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escaparHtml(texto: string): string {
  return texto.replace(/[&<>"']/g, (c) => ENTIDADES[c]);
}
