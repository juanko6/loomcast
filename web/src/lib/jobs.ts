// Cómo se lee la cola en la interfaz: el nombre de cada tipo de job y el
// resultado de uno terminado.
//
// `ETAPA_VIDEO` (proyectos.ts) dice algo parecido en gerundio y solo para el
// pipeline de vídeo, porque es lo que se enseña dentro de un proyecto mientras
// trabaja. Aquí hace falta en seco, y de las tres secciones: el panel de la
// cola mezcla imágenes, música y vídeo.
export const NOMBRE_JOB: Record<string, string> = {
  generar_ideas: "Ideas",
  generar_guion: "Guion",
  generar_metadatos: "Metadatos",
  crear_voz: "Voz nueva",
  clonar_voz: "Clonado de voz",
  generar_voz: "Narración",
  generar_subtitulos: "Subtítulos",
  generar_casting: "Reparto",
  generar_retrato: "Retrato de personaje",
  generar_retratos: "Retratos del reparto",
  generar_escenas: "Escenas",
  generar_imagenes: "Imágenes de escena",
  regenerar_imagen: "Imagen de una escena",
  mejorar_prompt_imagen: "Prompt de imagen",
  generar_previews_imagen: "Previews de imagen",
  generar_final_imagen: "Imagen final",
  quitar_fondo: "Quitar fondo",
  mejorar_prompt_musica: "Idea musical",
  generar_musica: "Pista de música",
  generar_musica_proyecto: "Música de la historia",
  generar_portada_musica: "Portada de la pista",
  regenerar_clip: "Clip de una escena",
  generar_clips_mixto: "Clips (modo por escena)",
  generar_upscale: "Reescalado",
  generar_clips: "Clips Ken Burns",
  generar_i2v: "Clips animados (i2v)",
  armar_video: "Montaje final",
  armar_estatico: "Montaje estático",
};

export function nombreJob(tipo: string): string {
  return NOMBRE_JOB[tipo] ?? tipo;
}

// "Parado" no se pinta como un error: el job no falló, se decidió pararlo, y
// mezclarlos haría dudar de si hay algo roto.
export const RESULTADO_JOB: Record<string, { texto: string; clase: string }> = {
  ok: { texto: "Hecho", clase: "text-ok" },
  error: { texto: "Error", clase: "text-danger" },
  cancelado: { texto: "Parado", clase: "text-warn" },
  corriendo: { texto: "En curso", clase: "text-accent" },
  pendiente: { texto: "En cola", clase: "text-dim" },
};

export function resultadoJob(estado: string) {
  return RESULTADO_JOB[estado] ?? { texto: estado, clase: "text-dim" };
}
