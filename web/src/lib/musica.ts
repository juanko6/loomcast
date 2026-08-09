// Cliente del modo Música. Refleja backend/routers/musica.py.
import { api } from "./api";
import type { MusicaResumen, TipoMusica } from "./types";

// Conditioning musical de ACE-Step 1.5: tempo, tonalidad y compás. Los tres son
// combos cerrados del nodo, así que el backend los normaliza antes de guardar.
export interface Musical {
  bpm: number;
  keyscale: string;
  timesig: string;
  idioma: string;
}

export interface MusicaDetalle extends Musical {
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

// Valores permitidos por TextEncodeAceStepAudio1.5 (ver
// backend/services/musica_combos.py).
export const RAICES = [
  "C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#",
  "Ab", "A", "A#", "Bb", "B",
] as const;

export const KEYSCALES = ["major", "minor"].flatMap((calidad) =>
  RAICES.map((raiz) => `${raiz} ${calidad}`),
);

export const TIMESIGS = ["2", "3", "4", "6"] as const;

// Solo los idiomas que se van a usar de verdad; el nodo acepta 51.
export const IDIOMAS = [
  { value: "es", label: "Español" },
  { value: "en", label: "Inglés" },
  { value: "pt", label: "Portugués" },
  { value: "fr", label: "Francés" },
  { value: "it", label: "Italiano" },
  { value: "de", label: "Alemán" },
  { value: "ja", label: "Japonés" },
] as const;

export const listarMusica = () => api<MusicaResumen[]>("/musica");

export const detalleMusica = (id: number) => api<MusicaDetalle>(`/musica/${id}`);

export const crearMusica = (
  body: {
    tipo: TipoMusica;
    idea: string;
    tags?: string;
    lyrics?: string;
    duracion_s: number;
  } & Partial<Musical>,
) => api<{ id: number }>("/musica", { method: "POST", body });

export const editarMusica = (
  id: number,
  body: { tags?: string; lyrics?: string; duracion_s?: number } & Partial<Musical>,
) => api<{ ok: boolean }>(`/musica/${id}`, { method: "PUT", body });

export const mejorarMusica = (id: number) =>
  api<{ job_id: number }>(`/musica/${id}/mejorar`, { method: "POST" });

export const generarMusica = (
  id: number,
  body: {
    tags?: string;
    lyrics?: string;
    duracion_s?: number;
    seed?: number | null;
  } & Partial<Musical>,
) => api<{ job_id: number }>(`/musica/${id}/generar`, { method: "POST", body });

export const borrarMusica = (id: number) =>
  api<{ borrada: number; archivos: number }>(`/musica/${id}`, { method: "DELETE" });
