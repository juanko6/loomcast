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

// Progreso del job que está corriendo (los demás lo traen a null). `pct` y
// `eta_s` van vacíos en las etapas que no van por lotes y hasta que termina el
// primer elemento, que es cuando hay algo medido con lo que estimar.
export interface ProgresoJob {
  job_id: number;
  transcurrido_s: number;
  fase: string;
  hecho: number;
  total: number;
  pct: number | null;
  eta_s: number | null;
}

export interface Job {
  id: number;
  tipo: string;
  estado: string;
  // Intentos gastados: la cola reintenta sola los fallos transitorios, así que
  // un 3 aquí quiere decir que lo de fuera falló tres veces.
  intentos: number;
  // Si esta etapa no se puede cortar a mitad, qué es lo que no se corta ("la
  // síntesis de la narración"); null en todas las demás. El botón de parada lo
  // dice en vez de aparentar que corta.
  sin_corte: string | null;
  progreso: ProgresoJob | null;
}

// Un job ya terminado, como lo devuelve /api/jobs/historial: "cancelado" es un
// estado propio porque pararlo fue una decisión, no un fallo.
export interface JobHistorial extends Job {
  log: string;
}

export interface TemaResumen {
  id: number;
  texto: string;
  n_ideas: number;
  n_aprobadas: number;
  // Nombre de la serie dueña del tema, o null en un tema normal. El de una
  // serie no se lista aparte: se entra a sus ideas de episodio desde la serie.
  serie?: string | null;
}

export interface ProyectoResumen {
  id: number;
  titulo: string;
  slug: string;
  estado: string;
  // Nombre de la serie de la que es episodio, o null si es un vídeo suelto.
  serie: string | null;
  // Número de episodio; 0 cuando no es un episodio.
  episodio: number;
  // Estado de su autopiloto si tiene uno en marcha, o null. El listado es desde
  // donde se ve que de diez vídeos tres están esperando que alguien los lea.
  autopiloto: string | null;
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
