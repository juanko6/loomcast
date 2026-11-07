// Cliente de los álbumes de música. Refleja backend/routers/albumes.py.
import { api, media } from "./api";

export interface AlbumResumen {
  id: number;
  titulo: string;
  // planificando | revision | produciendo
  estado: string;
  num_pistas: number;
  generadas: number;
  tiene_portada: boolean;
  ocupado: boolean;
}

export interface PistaAlbum {
  id: number;
  pista_n: number;
  titulo: string;
  // Ficha editable: la escena, el papel, el lead, la forma y la energía.
  intencion: string;
  tags: string | null;
  lyrics: string | null;
  bpm: number;
  keyscale: string;
  timesig: string;
  // Sale de los compases del guion y el tempo, no la elige nadie.
  duracion_s: number;
  compases: number;
  estado: string;
  seed: number | null;
  origen: boolean;
  escrita: boolean;
  tiene_audio: boolean;
  tiene_portada: boolean;
  ocupado: boolean;
}

export interface AlbumDetalle {
  id: number;
  titulo: string;
  idea: string;
  num_pistas: number;
  origen_musica_id: number | null;
  genero: string;
  banda: string[];
  firma: string;
  arco: string;
  seed: number;
  estado: string;
  tiene_portada: boolean;
  ocupado: boolean;
  duracion_total_s: number;
  pistas: PistaAlbum[];
}

export type CambiosPista = Partial<
  Pick<PistaAlbum, "titulo" | "intencion" | "bpm" | "keyscale" | "timesig">
>;

export const portadaAlbumUrl = (id: number) => media(`/albumes/${id}/portada`);

export const listarAlbumes = () => api<AlbumResumen[]>("/albumes");

export const detalleAlbum = (id: number) => api<AlbumDetalle>(`/albumes/${id}`);

export const crearAlbum = (body: { idea?: string; musica_id?: number; num_pistas: number }) =>
  api<{ id: number }>("/albumes", { method: "POST", body });

export const editarAlbum = (id: number, body: { titulo?: string; firma?: string }) =>
  api<{ ok: boolean }>(`/albumes/${id}`, { method: "PUT", body });

export const borrarAlbum = (id: number) =>
  api<{ borrado: number; pistas_borradas: number }>(`/albumes/${id}`, { method: "DELETE" });

export const replanificarAlbum = (id: number) =>
  api<{ job_id: number }>(`/albumes/${id}/replanificar`, { method: "POST" });

export const producirAlbum = (id: number) =>
  api<{ pistas: number; jobs: number[] }>(`/albumes/${id}/producir`, { method: "POST" });

export const ordenarAlbum = (id: number, ids: number[]) =>
  api<{ ok: boolean }>(`/albumes/${id}/orden`, { method: "PUT", body: { ids } });

export const editarPista = (id: number, musicaId: number, body: CambiosPista) =>
  api<{ ok: boolean }>(`/albumes/${id}/pistas/${musicaId}`, { method: "PUT", body });

export const reescribirPista = (id: number, musicaId: number) =>
  api<{ job_id: number }>(`/albumes/${id}/pistas/${musicaId}/reescribir`, { method: "POST" });

export const quitarPista = (id: number, musicaId: number) =>
  api<{ ok: boolean }>(`/albumes/${id}/pistas/${musicaId}`, { method: "DELETE" });

// "3:05" desde segundos.
export const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
