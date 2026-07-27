// Cliente del modo Música. Refleja backend/routers/musica.py.
import { api } from "./api";
import type { MusicaResumen, TipoMusica } from "./types";

export interface MusicaDetalle {
  id: number;
  tipo: TipoMusica;
  idea: string;
  tags: string;
  lyrics: string;
  duracion_s: number;
  seed: number | null;
  estado: string;
  tiene_audio: boolean;
  ocupado: boolean;
}

export const listarMusica = () => api<MusicaResumen[]>("/musica");

export const detalleMusica = (id: number) => api<MusicaDetalle>(`/musica/${id}`);

export const crearMusica = (body: {
  tipo: TipoMusica;
  idea: string;
  tags?: string;
  lyrics?: string;
  duracion_s: number;
}) => api<{ id: number }>("/musica", { method: "POST", body });

export const editarMusica = (
  id: number,
  body: { tags?: string; lyrics?: string; duracion_s?: number },
) => api<{ ok: boolean }>(`/musica/${id}`, { method: "PUT", body });

export const mejorarMusica = (id: number) =>
  api<{ job_id: number }>(`/musica/${id}/mejorar`, { method: "POST" });

export const generarMusica = (
  id: number,
  body: { tags?: string; lyrics?: string; duracion_s?: number; seed?: number | null },
) => api<{ job_id: number }>(`/musica/${id}/generar`, { method: "POST", body });

export const borrarMusica = (id: number) =>
  api<{ borrada: number; archivos: number }>(`/musica/${id}`, { method: "DELETE" });
