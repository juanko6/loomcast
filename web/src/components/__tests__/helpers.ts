import { createRawSnippet } from "svelte";

/** Snippet de texto plano, para los componentes que reciben `children`. */
export const texto = (t: string) =>
  createRawSnippet(() => ({ render: () => `<span>${t}</span>` }));
