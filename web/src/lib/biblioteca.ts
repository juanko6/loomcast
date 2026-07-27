// Biblioteca: vista unificada de todo lo creado. No tiene endpoints propios;
// agrega las listas de proyectos, galería y música en un tipo común.
import { media } from "./api";
import { listarProyectos } from "./proyectos";
import { listarGaleria } from "./galeria";
import { listarMusica } from "./musica";
import type { StudioMode } from "./types";

export type LibKind = "video" | "imagen" | "musica";

export interface LibItem {
  kind: LibKind;
  id: number;
  titulo: string;
  estado: string;
  // Etiqueta del subtipo (ej. "Editar", "Instrumental"); null en vídeos.
  subtipo: string | null;
  // Miniatura, si la hay. Los vídeos usan la imagen de su primera escena.
  thumb: string | null;
  // Recurso reproducible/descargable cuando existe.
  src: string | null;
  // Modo del estudio al que salta al abrirlo.
  destino: StudioMode;
}

const TIPO_IMAGEN: Record<string, string> = {
  generar: "Generar",
  editar: "Editar",
  quitarfondo: "Quitar fondo",
};

const TIPO_MUSICA: Record<string, string> = {
  instrumental: "Instrumental",
  cancion: "Canción",
};

export async function cargarBiblioteca(): Promise<LibItem[]> {
  const [proyectos, imagenes, musica] = await Promise.all([
    listarProyectos(),
    listarGaleria(),
    listarMusica(),
  ]);

  const items: LibItem[] = [
    ...proyectos.map((p): LibItem => ({
      kind: "video",
      id: p.id,
      titulo: p.titulo || p.slug,
      estado: p.estado,
      subtipo: null,
      // La escena 0 sirve de portada; si aún no existe, la <img> se oculta.
      thumb: media(`/proyectos/${p.id}/imagenes/0`),
      src: p.estado === "final" ? media(`/proyectos/${p.id}/video`) : null,
      destino: "videos",
    })),
    ...imagenes.map((g): LibItem => ({
      kind: "imagen",
      id: g.id,
      titulo: g.idea || "(imagen)",
      estado: g.estado,
      subtipo: TIPO_IMAGEN[g.tipo] ?? g.tipo,
      thumb:
        g.estado === "final"
          ? media(`/galeria/${g.id}/final`)
          : media(`/galeria/${g.id}/fuente`),
      src: g.estado === "final" ? media(`/galeria/${g.id}/final`) : null,
      destino: "imagenes",
    })),
    ...musica.map((m): LibItem => ({
      kind: "musica",
      id: m.id,
      titulo: m.idea || "(pista)",
      estado: m.estado,
      subtipo: TIPO_MUSICA[m.tipo] ?? m.tipo,
      thumb: null,
      src: m.estado === "generada" ? media(`/musica/${m.id}/audio`) : null,
      destino: "musica",
    })),
  ];

  return items;
}

export const FILTROS: { id: "todo" | LibKind; label: string }[] = [
  { id: "todo", label: "Todo" },
  { id: "video", label: "Vídeos" },
  { id: "imagen", label: "Imágenes" },
  { id: "musica", label: "Música" },
];
