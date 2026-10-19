<script lang="ts">
  // Botón de parada. Vive en la cabecera y en las tres secciones, porque es
  // donde se está mirando cuando uno decide que ya no quiere eso.
  //
  // Parar es destructivo: se confirma como los borrados de VideoStudio, y el
  // aviso dice exactamente qué se pierde (lo que esté a medio hacer) y qué se
  // conserva (todo lo que ya estaba terminado).
  import Button from "../primitives/Button.svelte";
  import { jobs, pararCola } from "@/lib/stores";

  let {
    soloCorriendo = false,
    etiqueta = "Parar",
    size = "sm",
  }: {
    // true = cortar solo la etapa en curso y dejar la cola esperando.
    soloCorriendo?: boolean;
    etiqueta?: string;
    size?: "sm" | "md";
  } = $props();

  let parando = $state(false);
  let error = $state("");

  const esperando = $derived($jobs.filter((j) => j.estado === "pendiente").length);
  // Lo que la etapa en curso no puede cortar a mitad (la síntesis de voz), para
  // no prometer en el aviso algo que no va a pasar.
  const sinCorte = $derived($jobs.find((j) => j.estado === "corriendo")?.sin_corte ?? null);

  const tarde = $derived(
    sinCorte
      ? `Ojo: ${sinCorte} ya está en marcha y no se puede cortar a mitad. ` +
        "Se para en cuanto termine, sin seguir con la etapa siguiente.\n\n"
      : "",
  );

  function aviso(): string {
    if (soloCorriendo) {
      return (
        "¿Detener lo que se está generando?\n\n" +
        tarde +
        "Se corta la etapa en curso y no se encadena la siguiente. " +
        "Lo que ya estaba terminado se conserva; lo que esté a medio hacer se descarta y hay que repetirlo.\n\n" +
        (esperando
          ? `Los ${esperando} trabajos que esperan en la cola siguen esperando.`
          : "La cola se queda vacía.")
      );
    }
    return (
      "¿Parar la generación y vaciar la cola?\n\n" +
      tarde +
      "Se corta lo que se está generando" +
      (esperando ? ` y se descartan los ${esperando} trabajos que esperan.` : ".") +
      "\n\nSe conserva todo lo ya terminado (las imágenes, los clips y las pistas completas); " +
      "lo que esté a medio hacer se descarta y hay que repetirlo."
    );
  }

  async function parar() {
    if (!confirm(aviso())) return;
    parando = true;
    error = "";
    try {
      await pararCola(soloCorriendo ? { pendientes: false } : {});
    } catch (e) {
      error = (e as Error).message;
    } finally {
      parando = false;
    }
  }
</script>

{#if $jobs.length}
  <Button
    variant="danger"
    {size}
    disabled={parando}
    onclick={parar}
    title={sinCorte
      ? `${sinCorte} no se puede cortar a mitad: se para en cuanto termine`
      : soloCorriendo
        ? "Detener la etapa en curso"
        : "Detener la generación y vaciar la cola"}
  >
    {parando ? "Parando…" : etiqueta}
  </Button>
{/if}
{#if error}
  <span class="text-xs text-danger">{error}</span>
{/if}
