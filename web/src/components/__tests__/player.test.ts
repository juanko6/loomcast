import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { currentTrack, isPlaying, playTrack, type PlayerTrack } from "@/lib/player";
import { modo } from "@/lib/stores";
import PlayerBar from "../player/PlayerBar.svelte";

// jsdom no implementa la reproducción: se sustituye lo mínimo del <audio>.
let play: ReturnType<typeof vi.spyOn>;
let pause: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  currentTrack.set(null);
  isPlaying.set(false);
  modo.set("videos");
  play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
});

const pista = (extra: Partial<PlayerTrack> = {}): PlayerTrack => ({
  id: 1, tipo: "instrumental", idea: "lofi", seed: null, duracion_s: 30, src: "/api/musica/1/audio", cover: null, ...extra,
});

describe("PlayerBar", () => {
  it("sin pista cargada no muestra la isla (pero el <audio> sigue montado)", () => {
    const { container } = render(PlayerBar);
    expect(screen.queryByRole("contentinfo")).toBeNull();
    expect(container.querySelector("audio")).not.toBeNull();
  });

  it("al cargar una pista aparece la isla con su título y tipo, y empieza a sonar", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista({ tipo: "cancion" }));

    expect(await screen.findByText("lofi")).toBeInTheDocument();
    expect(screen.getByText("Canción")).toBeInTheDocument();
    await waitFor(() => expect(play).toHaveBeenCalled());
    expect(container.querySelector("audio")!.getAttribute("src")).toBe("/api/musica/1/audio");
  });

  it("sin título muestra '(pista)'", async () => {
    render(PlayerBar);
    playTrack(pista({ idea: "" }));
    expect(await screen.findByText("(pista)")).toBeInTheDocument();
  });

  it("el botón principal alterna reproducir/pausar según el estado del <audio>", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista());
    await screen.findByText("lofi");

    const audio = container.querySelector("audio")!;
    audio.dispatchEvent(new Event("play"));
    expect(await screen.findByRole("button", { name: "Pausar" })).toBeInTheDocument();
    audio.dispatchEvent(new Event("pause"));
    expect(await screen.findByRole("button", { name: "Reproducir" })).toBeInTheDocument();
    audio.dispatchEvent(new Event("play"));
    audio.dispatchEvent(new Event("ended"));
    expect(get(isPlaying)).toBe(false);
  });

  it("pulsar el botón principal alterna la reproducción", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista());
    await screen.findByText("lofi");
    play.mockClear();
    Object.defineProperty(container.querySelector("audio")!, "paused", { value: true, configurable: true });
    await userEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(play).toHaveBeenCalled();
  });

  it("muestra el tiempo actual y la duración con formato m:ss", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista());
    await screen.findByText("lofi");
    const audio = container.querySelector("audio")!;
    Object.defineProperty(audio, "duration", { value: 125, configurable: true });
    Object.defineProperty(audio, "currentTime", { value: 65, writable: true, configurable: true });
    audio.dispatchEvent(new Event("loadedmetadata"));
    audio.dispatchEvent(new Event("timeupdate"));
    expect(await screen.findByText("2:05")).toBeInTheDocument();
    expect(screen.getByText("1:05")).toBeInTheDocument();
  });

  it("una duración no finita (stream sin metadatos) se muestra como 0:00", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista());
    await screen.findByText("lofi");
    const audio = container.querySelector("audio")!;
    Object.defineProperty(audio, "duration", { value: Infinity, configurable: true });
    audio.dispatchEvent(new Event("loadedmetadata"));
    expect(screen.getAllByText("0:00").length).toBeGreaterThan(0);
  });

  it("arrastrar la barra de posición busca en el audio", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista());
    await screen.findByText("lofi");
    const audio = container.querySelector("audio")!;
    Object.defineProperty(audio, "duration", { value: 100, configurable: true });
    Object.defineProperty(audio, "currentTime", { value: 0, writable: true, configurable: true });
    audio.dispatchEvent(new Event("loadedmetadata"));

    await screen.findByText("1:40");   // el máximo del <input range> llega con la duración
    const barra = screen.getByLabelText("Posición de reproducción") as HTMLInputElement;
    barra.value = "40";
    barra.dispatchEvent(new Event("input", { bubbles: true }));

    expect(audio.currentTime).toBe(40);
  });

  it("descarga apunta al audio de la pista", async () => {
    render(PlayerBar);
    playTrack(pista({ id: 9, src: "/api/musica/9/audio" }));
    const enlace = await screen.findByRole("link", { name: "Descargar" });
    expect(enlace).toHaveAttribute("href", "/api/musica/9/audio");
    expect(enlace).toHaveAttribute("download", "loomcast_musica_9");
  });

  it("cerrar detiene el audio y oculta la isla", async () => {
    render(PlayerBar);
    playTrack(pista());
    await userEvent.click(await screen.findByRole("button", { name: "Detener y cerrar" }));
    expect(get(currentTrack)).toBeNull();
    expect(screen.queryByText("lofi")).toBeNull();
    expect(pause).toHaveBeenCalled();
  });

  it("cambiar de pista recarga el audio con la nueva fuente", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista({ id: 1, src: "/a1" }));
    await screen.findByText("lofi");
    playTrack(pista({ id: 2, idea: "jazz", src: "/a2" }));
    expect(await screen.findByText("jazz")).toBeInTheDocument();
    expect(container.querySelector("audio")!.getAttribute("src")).toBe("/a2");
  });

  it("en el modo Música se aparta del panel de detalle de la derecha", async () => {
    modo.set("musica");
    const { container } = render(PlayerBar);
    playTrack(pista());
    await screen.findByText("lofi");
    expect((container.querySelector(".absolute") as HTMLElement).style.right).toBe("352px");
  });

  it("en los demás modos ocupa todo el ancho útil", async () => {
    const { container } = render(PlayerBar);
    playTrack(pista());
    await screen.findByText("lofi");
    expect((container.querySelector(".absolute") as HTMLElement).style.right).toBe("12px");
  });
});
