// Cliente del área de Series (dentro del modo Vídeos): refleja
// backend/routers/series.py.
//
// Una serie es un nombre, una plantilla y un reparto fijo. Lo que la UI tiene
// que dejar hacer en un clic es lo que más se repite al producir una serie de
// verdad: el episodio siguiente.
import { api } from "./api";
import type { MiembroReparto } from "./proyectos";

export interface SerieResumen {
  id: number;
  slug: string;
  nombre: string;
  plantilla: string;
  // Tema del que cuelgan las ideas de episodio: con él se reutiliza el "generar
  // más ideas" de siempre, solo que con el prompt de ideas de la plantilla de
  // serie, que piensa en episodios.
  tema_id: number;
  n_episodios: number;
  n_miembros: number;
}

export interface EpisodioResumen {
  proyecto_id: number;
  episodio: number;
  titulo: string;
  slug: string;
  estado: string;
  // Vacío = sin cerrar. Cuando lo tiene, es lo que el episodio siguiente usará
  // como contexto al escribir su guion.
  resumen: string;
  ocupado: boolean;
}

export interface SerieDetalle extends SerieResumen {
  // El reparto fijo, tal como está en el reparto propio: cada episodio nuevo se
  // los trae con su ficha, su cara y su voz.
  miembros: MiembroReparto[];
  episodios: EpisodioResumen[];
}

export const listarSeries = () => api<SerieResumen[]>("/series");
export const crearSerie = (nombre: string, plantilla: string) =>
  api<SerieResumen>("/series", { method: "POST", body: { nombre, plantilla } });
export const detalleSerie = (id: number) => api<SerieDetalle>(`/series/${id}`);
export const borrarSerie = (id: number) =>
  api<{ episodios_sueltos: number }>(`/series/${id}`, { method: "DELETE" });

export const anadirMiembroSerie = (id: number, reparto_slug: string) =>
  api<{ slug: string }>(`/series/${id}/miembros`, {
    method: "POST",
    body: { reparto_slug },
  });
export const quitarMiembroSerie = (id: number, slug: string) =>
  api<{ slug: string }>(`/series/${id}/miembros/${slug}`, { method: "DELETE" });

// `apunte` es opcional: vacío, el episodio lo propone el LLM desde el resumen
// del anterior. `reparto_traido` dice con qué clave entró cada personaje fijo,
// que es el marcador que acabará en los prompts de escena.
export const crearEpisodio = (id: number, apunte = "") =>
  api<{
    proyecto_id: number;
    episodio: number;
    idea_id: number;
    job_id?: number;
    reparto_traido: string[];
  }>(`/series/${id}/episodios`, { method: "POST", body: { apunte } });
