import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/musica", async (o) => ({
  ...(await o<typeof import("@/lib/musica")>()),
  listarMusica: vi.fn(), detalleMusica: vi.fn(),
}));
vi.mock("@/lib/albumes", async (o) => ({
  ...(await o<typeof import("@/lib/albumes")>()),
  listarAlbumes: vi.fn(), detalleAlbum: vi.fn(), crearAlbum: vi.fn(), producirAlbum: vi.fn(),
}));
vi.mock("@/lib/api", async (o) => ({ ...(await o<typeof import("@/lib/api")>()), api: vi.fn().mockResolvedValue([]) }));

import * as m from "@/lib/musica";
import * as al from "@/lib/albumes";
import type { AlbumDetalle, PistaAlbum } from "@/lib/albumes";
import type { MusicaDetalle } from "@/lib/musica";
import AlbumView from "../musica/AlbumView.svelte";
import MusicStudio from "../musica/MusicStudio.svelte";
import TrackDetail from "../musica/TrackDetail.svelte";

const pista = (id: number, extra: Partial<PistaAlbum> = {}): PistaAlbum => ({
  id, pista_n: id, titulo: `Tema ${id}`, intencion: `Una escena ${id}\nPapel: ballad`,
  tags: "noir jazz", lyrics: "[Intro - 4 bars - x]", bpm: 80, keyscale: "D minor", timesig: "4",
  duracion_s: 185, compases: 60, estado: "nueva", seed: 7, origen: false, escrita: true,
  tiene_audio: false, tiene_portada: false, ocupado: false, ...extra,
});
const album = (extra: Partial<AlbumDetalle> = {}): AlbumDetalle => ({
  id: 3, titulo: "Noches de neón", idea: "jazz", num_pistas: 2, origen_musica_id: null,
  genero: "noir jazz", banda: ["tenor sax", "piano"], firma: "Recorded live.", arco: "",
  seed: 7, estado: "revision", tiene_portada: false, ocupado: false, duracion_total_s: 370,
  pistas: [pista(1), pista(2)], ...extra,
});

beforeEach(() => {
  vi.mocked(m.listarMusica).mockResolvedValue([
    { id: 1, idea: "suelta", tipo: "instrumental", estado: "generada", tiene_portada: false, album_id: null },
    { id: 9, idea: "del álbum", tipo: "instrumental", estado: "nueva", tiene_portada: false, album_id: 3 },
  ]);
  vi.mocked(al.listarAlbumes).mockResolvedValue([
    { id: 3, titulo: "Noches de neón", estado: "revision", num_pistas: 2, generadas: 0, tiene_portada: false, ocupado: false },
  ]);
  vi.mocked(al.detalleAlbum).mockResolvedValue(album());
});

describe("MusicStudio con álbumes", () => {
  it("la lista de pistas no enseña las de un álbum", async () => {
    render(MusicStudio);
    expect(await screen.findByText("suelta")).toBeInTheDocument();
    expect(screen.queryByText("del álbum")).not.toBeInTheDocument();
  });

  it("abre un álbum y enseña su tracklist con la duración del guion", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByRole("tab", { name: "Álbumes" }));
    await userEvent.click(await screen.findByText("Noches de neón"));
    expect(await screen.findByText("Tema 1")).toBeInTheDocument();
    expect(screen.getAllByText("3:05 · 60 c.")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Producir 2 pistas" })).toBeEnabled();
  });

  it("planifica un álbum desde una idea", async () => {
    vi.mocked(al.crearAlbum).mockResolvedValue({ id: 3 });
    render(MusicStudio);
    await userEvent.click(await screen.findByRole("tab", { name: "Álbumes" }));
    await userEvent.type(screen.getByRole("textbox"), "lofi de lluvia");
    await userEvent.click(screen.getByRole("button", { name: "Planificar álbum" }));
    await waitFor(() => expect(al.crearAlbum).toHaveBeenCalledWith({ idea: "lofi de lluvia", num_pistas: 12 }));
  });
});

describe("AlbumView", () => {
  it("al guardar solo manda lo que cambió", async () => {
    const onedit = vi.fn();
    render(AlbumView, {
      album: album(), onselect: vi.fn(), onedit, onrewrite: vi.fn(), onmove: vi.fn(), onremove: vi.fn(),
    });
    await userEvent.click(screen.getByText("Tema 1"));
    const bpm = screen.getByTitle("Tempo (BPM)");
    await userEvent.clear(bpm);
    await userEvent.type(bpm, "96");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onedit).toHaveBeenCalledWith(1, { bpm: 96 });
  });

  it("la pista de origen no se reescribe", async () => {
    render(AlbumView, {
      album: album({ pistas: [pista(1, { origen: true })] }),
      onselect: vi.fn(), onedit: vi.fn(), onrewrite: vi.fn(), onmove: vi.fn(), onremove: vi.fn(),
    });
    await userEvent.click(screen.getByText("Tema 1"));
    expect(screen.queryByRole("button", { name: "Reescribir con LLM" })).not.toBeInTheDocument();
  });
});

describe("TrackDetail", () => {
  const detalle = (extra: Partial<MusicaDetalle> = {}): MusicaDetalle => ({
    id: 4, tipo: "instrumental", idea: "jazz", tags: "x", lyrics: "", duracion_s: 60, seed: 1,
    estado: "generada", tiene_audio: true, tiene_portada: false, ocupado: false,
    bpm: 90, keyscale: "A minor", timesig: "4", idioma: "en", album_id: null, ...extra,
  });

  it("ofrece crear un álbum desde una pista instrumental que ya suena", async () => {
    const oncreatealbum = vi.fn();
    render(TrackDetail, { detail: detalle(), oncreatealbum });
    await userEvent.click(screen.getByRole("button", { name: "Crear álbum" }));
    expect(oncreatealbum).toHaveBeenCalledWith(12);
  });

  it("no lo ofrece en una canción ni en una pista que ya es de un álbum", () => {
    const { unmount } = render(TrackDetail, { detail: detalle({ tipo: "cancion" }), oncreatealbum: vi.fn() });
    expect(screen.queryByRole("button", { name: "Crear álbum" })).not.toBeInTheDocument();
    unmount();
    render(TrackDetail, { detail: detalle({ album_id: 3 }), oncreatealbum: vi.fn() });
    expect(screen.queryByRole("button", { name: "Crear álbum" })).not.toBeInTheDocument();
  });
});
