// Registro central de iconos (paths SVG de 24×24, trazo). Un solo sitio para
// mantener la iconografía coherente en todos los modos. Los que deben ir
// rellenos (play/pause/like activo) se marcan en `filled`.
export const icons = {
  play: "M7 4.5v15l12-7.5-12-7.5Z",
  pause: "M8 5v14M16 5v14",
  download: "M12 3v12m0 0 4-4m-4 4-4-4M5 21h14",
  share: "M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7M16 6l-4-4-4 4M12 2v13",
  heart:
    "M12 20s-7-4.4-9.3-8.7C1.2 8 2.7 4.6 6 4.6c2 0 3.2 1.1 4 2.1.8-1 2-2.1 4-2.1 3.3 0 4.8 3.4 3.3 6.7C19 15.6 12 20 12 20Z",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z",
  music: "M9 18V6l11-2v12M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm11-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  image:
    "M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1ZM3 16l5-5 4 4 3-3 6 6M9 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z",
  volume: "M11 5 6 9H2v6h4l5 4V5ZM19 5a9 9 0 0 1 0 14M15.5 8.5a5 5 0 0 1 0 7",
  clapper:
    "M3 8h18M3 8l1.5-4h15L21 8M3 8v11a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V8M7 4l-1 4M12 4l-1 4M17 4l-1 4",
  x: "M6 6l12 12M18 6 6 18",
} as const;

export type IconName = keyof typeof icons;

// Iconos que se dibujan rellenos (fill) en vez de solo trazo.
export const filledIcons: IconName[] = ["play"];
