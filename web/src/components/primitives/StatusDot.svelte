<script lang="ts">
  // Indicador de estado con forma + color + texto (no solo color, por
  // accesibilidad). `estado` mapea a la semántica del sistema.
  type Estado = "on" | "off" | "espera";
  let {
    estado = "off",
    label,
    title,
  }: { estado?: Estado; label: string; title?: string } = $props();

  const estilos: Record<Estado, string> = {
    on: "bg-ok-soft text-ok",
    off: "bg-danger-soft text-danger",
    espera: "bg-warn-soft text-warn",
  };
  const punto: Record<Estado, string> = {
    on: "bg-ok",
    off: "bg-danger",
    espera: "bg-warn",
  };
</script>

<span
  {title}
  class={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${estilos[estado]}`}
>
  <span class={`size-1.5 rounded-full ${punto[estado]}`}></span>
  {label}
</span>
