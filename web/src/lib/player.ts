// Player de audio global y persistente. El <audio> real vive una sola vez en
// PlayerBar (dentro de App, fuera del workspace), así la reproducción NO se
// corta al cambiar de pista ni de modo. El control es imperativo y directo
// sobre el elemento (registrado por PlayerBar): sencillo y sin sorpresas.
import { writable, get } from "svelte/store";
import type { TipoMusica } from "./types";

export interface PlayerTrack {
  id: number;
  tipo: TipoMusica;
  idea: string;
  seed: number | null;
  duracion_s: number;
  // Origen del audio (ruta /api/...). Futuro: `cover` para la portada IA.
  src: string;
}

// Pista cargada en el player (null = nada sonando, la isla se oculta).
export const currentTrack = writable<PlayerTrack | null>(null);
// ¿Está reproduciéndose ahora mismo? Lo actualiza PlayerBar según el <audio>.
export const isPlaying = writable(false);

// Referencia al <audio> real, que PlayerBar registra al montarse. Permite que
// los controles (desde cualquier card o el detalle) actúen directamente.
let audioEl: HTMLAudioElement | null = null;
export function registerAudio(el: HTMLAudioElement | null): void {
  audioEl = el;
}

// Carga una pista y reproduce. Si ya es la que está cargada, alterna play/pausa.
// (La carga+reproducción de una pista NUEVA la ejecuta PlayerBar al cambiar
// `currentTrack`; aquí solo fijamos el estado.)
export function playTrack(track: PlayerTrack): void {
  if (get(currentTrack)?.id === track.id) {
    toggle();
    return;
  }
  currentTrack.set(track);
}

export function toggle(): void {
  if (!audioEl) return;
  if (audioEl.paused) audioEl.play().catch(() => {});
  else audioEl.pause();
}

// Detiene por completo y cierra la isla (vacía la pista cargada).
export function stop(): void {
  if (audioEl) {
    audioEl.pause();
    audioEl.removeAttribute("src");
    audioEl.load();
  }
  currentTrack.set(null);
  isPlaying.set(false);
}

export function isCurrent(id: number): boolean {
  return get(currentTrack)?.id === id;
}
