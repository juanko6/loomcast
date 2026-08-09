// Contratos de la API que consume la UI. Reflejan lo que devuelven los routers
// de FastAPI; se amplían a medida que cada modo se porta a Astro.

export type LlmEstado = "activo" | "cargado" | "en_espera" | "caido";

export interface Salud {
  llm_estado: { estado: LlmEstado; nombre: string };
  comfy: boolean;
}

export interface ModeloLLM {
  id: string;
  nombre: string;
}

export interface Job {
  id: number;
  tipo: string;
  estado: string;
}

export interface TemaResumen {
  id: number;
  texto: string;
  n_ideas: number;
  n_aprobadas: number;
}

export interface ProyectoResumen {
  id: number;
  titulo: string;
  slug: string;
  estado: string;
}

export type TipoGaleria = "generar" | "editar" | "quitarfondo";
export interface GaleriaResumen {
  id: number;
  idea: string;
  tipo: TipoGaleria;
  estado: string;
}

export type TipoMusica = "instrumental" | "cancion";
export interface MusicaResumen {
  id: number;
  idea: string;
  tipo: TipoMusica;
  estado: string;
  // La portada la genera el LLM+motor de imagen al pedir la sugerencia; hasta
  // entonces la miniatura cae al icono por defecto.
  tiene_portada: boolean;
}

// Modos de nivel superior del estudio (el rail izquierdo).
export type StudioMode = "videos" | "imagenes" | "musica" | "biblioteca";
