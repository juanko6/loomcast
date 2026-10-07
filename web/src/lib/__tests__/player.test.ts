import { beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import {
  currentTrack,
  isCurrent,
  isPlaying,
  playTrack,
  registerAudio,
  stop,
  toggle,
  type PlayerTrack,
} from "../player";

const pista = (id: number): PlayerTrack => ({
  id, tipo: "instrumental", idea: "lofi", seed: null, duracion_s: 30,
  src: `/api/musica/${id}/audio`, cover: null,
});

function audioFalso(paused = true) {
  return {
    paused,
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
    load: vi.fn(),
    removeAttribute: vi.fn(),
  } as unknown as HTMLAudioElement & Record<string, ReturnType<typeof vi.fn>>;
}

beforeEach(() => {
  registerAudio(null);
  currentTrack.set(null);
  isPlaying.set(false);
});

describe("playTrack", () => {
  it("carga una pista nueva", () => {
    playTrack(pista(1));
    expect(get(currentTrack)?.id).toBe(1);
    expect(isCurrent(1)).toBe(true);
    expect(isCurrent(2)).toBe(false);
  });

  it("cambiar de pista sustituye la anterior", () => {
    playTrack(pista(1));
    playTrack(pista(2));
    expect(get(currentTrack)?.id).toBe(2);
  });

  it("volver a pulsar la pista actual alterna play/pausa en vez de recargarla", () => {
    const audio = audioFalso(true);
    registerAudio(audio);
    playTrack(pista(1));
    playTrack(pista(1));
    expect(audio.play).toHaveBeenCalledTimes(1);
    expect(get(currentTrack)?.id).toBe(1);
  });
});

describe("toggle", () => {
  it("sin <audio> registrado no hace nada ni lanza", () => {
    expect(() => toggle()).not.toThrow();
  });

  it("pausado → reproduce; sonando → pausa", () => {
    const audio = audioFalso(true);
    registerAudio(audio);
    toggle();
    expect(audio.play).toHaveBeenCalled();
    (audio as { paused: boolean }).paused = false;
    toggle();
    expect(audio.pause).toHaveBeenCalled();
  });

  it("un play() rechazado por el navegador (autoplay) no revienta", async () => {
    const audio = audioFalso(true);
    audio.play = vi.fn().mockRejectedValue(new DOMException("NotAllowed"));
    registerAudio(audio);
    expect(() => toggle()).not.toThrow();
    await Promise.resolve();
  });
});

describe("stop", () => {
  it("detiene el audio, vacía su fuente y cierra la isla", () => {
    const audio = audioFalso(false);
    registerAudio(audio);
    playTrack(pista(1));
    isPlaying.set(true);

    stop();

    expect(audio.pause).toHaveBeenCalled();
    expect(audio.removeAttribute).toHaveBeenCalledWith("src");
    expect(audio.load).toHaveBeenCalled();
    expect(get(currentTrack)).toBeNull();
    expect(get(isPlaying)).toBe(false);
  });

  it("sin <audio> igualmente limpia el estado", () => {
    playTrack(pista(1));
    isPlaying.set(true);
    stop();
    expect(get(currentTrack)).toBeNull();
    expect(get(isPlaying)).toBe(false);
  });
});
