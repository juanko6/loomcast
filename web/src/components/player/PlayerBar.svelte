<script lang="ts">
  import Thumbnail from "../primitives/Thumbnail.svelte";
  import IconButton from "../primitives/IconButton.svelte";
  import Icon from "../primitives/Icon.svelte";
  import Chip from "../primitives/Chip.svelte";
  import { modo } from "@/lib/stores";
  import {
    currentTrack,
    isPlaying,
    registerAudio,
    toggle,
    stop,
  } from "@/lib/player";

  // El <audio> real: uno solo, siempre montado, fuera del workspace. Por eso la
  // reproducción sobrevive a cambiar de pista y de modo.
  let audio = $state<HTMLAudioElement>();
  let cur = $state(0);
  let dur = $state(0);
  let loadedId = -1;

  // La isla flota solo sobre las columnas internas (config + lista): se aparta
  // del rail (izquierda) y, en Música, del panel de detalle (derecha).
  const RAIL = 248;
  const DETAIL = 340;
  const insetDerecha = $derived($modo === "musica" ? DETAIL : 0);

  // Registrar el elemento para que los controles imperativos lo manejen.
  $effect(() => {
    registerAudio(audio ?? null);
  });

  // Cargar y reproducir cuando cambia la pista cargada. Si es la misma id, no
  // recargamos (toggle no toca currentTrack, así que este efecto no corre).
  $effect(() => {
    const t = $currentTrack;
    if (!audio || !t) return;
    if (t.id !== loadedId) {
      loadedId = t.id;
      audio.src = t.src;
      cur = 0;
    }
    audio.play().catch(() => {});
  });

  function fmt(s: number): string {
    if (!Number.isFinite(s)) return "0:00";
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60);
    return `${m}:${r.toString().padStart(2, "0")}`;
  }

  function seek(e: Event) {
    const v = +(e.target as HTMLInputElement).value;
    if (audio) audio.currentTime = v;
    cur = v;
  }

  const tipoLabel = $derived($currentTrack?.tipo === "cancion" ? "Canción" : "Instrumental");
  const pct = $derived(dur ? (cur / dur) * 100 : 0);

  // --- Acciones futuras (stubs, listas para cablear) ---
  // TODO(feature): enviar/compartir/like requieren backend (persistir like,
  // endpoint de compartir, integración de envío). Por ahora no hacen nada.
  function proximamente() {}
</script>

<!-- Audio siempre montado (aunque no haya nada sonando) -->
<audio
  bind:this={audio}
  onplay={() => isPlaying.set(true)}
  onpause={() => isPlaying.set(false)}
  onended={() => isPlaying.set(false)}
  ontimeupdate={() => (cur = audio?.currentTime ?? 0)}
  onloadedmetadata={() => (dur = audio?.duration ?? 0)}
  class="hidden"
></audio>

{#if $currentTrack}
  <!-- Contenedor de posición: acota la isla a las columnas internas -->
  <div
    class="pointer-events-none absolute bottom-3 z-30"
    style={`left:${RAIL + 12}px; right:${insetDerecha + 12}px`}
  >
    <!-- Isla glass: translúcida + desenfoque del contenido de detrás -->
    <footer
      class="pointer-events-auto flex h-16 items-center gap-4 rounded-2xl border border-line/70
             bg-surface/70 px-4 shadow-panel backdrop-blur-xl"
    >
      <!-- Pista sonando -->
      <div class="flex min-w-0 items-center gap-3" style="width:236px">
        <Thumbnail src={$currentTrack.cover} alt="" icon="music" size={44} />
        <div class="min-w-0">
          <p class="truncate text-sm font-medium text-text">{$currentTrack.idea || "(pista)"}</p>
          <div class="mt-0.5 flex items-center gap-1.5">
            <Chip tone="accent">{tipoLabel}</Chip>
          </div>
        </div>
      </div>

      <!-- Transporte + progreso -->
      <div class="flex min-w-0 flex-1 items-center gap-3">
        <button
          type="button"
          onclick={toggle}
          aria-label={$isPlaying ? "Pausar" : "Reproducir"}
          class="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-on-accent
                 transition hover:bg-accent-hover"
        >
          <Icon name={$isPlaying ? "pause" : "play"} size={16} />
        </button>
        <span class="w-9 shrink-0 text-right text-xs tabular-nums text-dim">{fmt(cur)}</span>
        <input
          type="range"
          class="scrub min-w-0 flex-1"
          min="0"
          max={dur || 0}
          step="0.1"
          value={cur}
          style={`--pct:${pct}%`}
          oninput={seek}
          aria-label="Posición de reproducción"
        />
        <span class="w-9 shrink-0 text-xs tabular-nums text-dim">{fmt(dur)}</span>
      </div>

      <!-- Acciones: descargar (real) + compartir/like (futuro) + cerrar -->
      <div class="flex shrink-0 items-center gap-0.5">
        <a
          href={$currentTrack.src}
          download={`loomcast_musica_${$currentTrack.id}`}
          title="Descargar"
          aria-label="Descargar"
          class="inline-grid place-items-center rounded-md p-2 text-dim transition-colors hover:bg-surface-3 hover:text-text"
        >
          <Icon name="download" size={18} />
        </a>
        <IconButton name="heart" label="Me gusta" soon onclick={proximamente} />
        <IconButton name="share" label="Compartir" soon onclick={proximamente} />
        <span class="mx-1 h-6 w-px bg-line"></span>
        <IconButton name="x" label="Detener y cerrar" onclick={stop} />
      </div>
    </footer>
  </div>
{/if}
