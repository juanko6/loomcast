<script lang="ts">
  // Isla raíz del estudio: posee el shell (rail + workspace) y arranca el
  // polling de salud/cola al montar. Astro solo aporta el documento y los
  // tokens; toda la interactividad vive dentro de este árbol Svelte.
  import { onMount } from "svelte";
  import Rail from "./shell/Rail.svelte";
  import Workspace from "./shell/Workspace.svelte";
  import PlayerBar from "./player/PlayerBar.svelte";
  import {
    iniciarPolling,
    detenerPolling,
    cargarModelos,
  } from "@/lib/stores";

  onMount(() => {
    cargarModelos().catch(() => {});
    iniciarPolling();
    return () => detenerPolling();
  });
</script>

<div class="relative flex h-dvh w-full overflow-hidden bg-bg text-text">
  <Rail />
  <Workspace />
  <!-- Isla de reproducción global: flota (posición absoluta) sobre el layout,
       fuera del workspace, así sobrevive a cambios de pista y de modo. Solo se
       muestra cuando hay algo cargado. -->
  <PlayerBar />
</div>
