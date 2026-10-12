#!/usr/bin/env bash
# Levanta Loomcast entero en una sola terminal: ComfyUI + backend, con los logs
# de ambos entremezclados y prefijados. Ctrl+C lo para todo de forma ordenada.
#
#   scripts/run-loomcast.sh              ComfyUI + backend; UI en 127.0.0.1:8700
#   scripts/run-loomcast.sh --lan        igual, pero accesible desde la red local
#   scripts/run-loomcast.sh --dev        añade Astro en 4321 con recarga en caliente
#   scripts/run-loomcast.sh --sin-comfy  solo el backend (ComfyUI lo llevas tú aparte)
#
# El frontend no es un proceso: uvicorn sirve el build de web/dist/, así que el
# script lo recompila solo si hay fuentes más nuevas que el build. Con --dev sí
# arranca Astro, y entonces la UI buena es la de 4321.
#
# El llama-server tampoco se arranca aquí: lo gestiona Loomcast según config.toml.

set -euo pipefail
set -m   # cada servicio en su propio grupo de procesos, para pararlo con sus hijos

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

COMFY_DIR="${COMFY_DIR:-$HOME/Documents/ComfyUI}"
PUERTO_BACK=8700
PUERTO_COMFY=8188
PUERTO_WEB=4321
HOST=127.0.0.1
DEV=0
CON_COMFY=1

while [ $# -gt 0 ]; do
  case "$1" in
    --lan)       HOST=0.0.0.0 ;;
    --dev)       DEV=1 ;;
    --sin-comfy) CON_COMFY=0 ;;
    -h|--help|--ayuda)
      # Hasta la última línea de la cabecera: con un rango fijo, tocar el
      # comentario de arriba acaba imprimiendo código.
      sed -n '2,/^$/p' "$0" | sed 's/^#\{1,\} \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $1 (prueba --ayuda)" >&2; exit 2 ;;
  esac
  shift
done

if [ -t 1 ]; then
  ROJO=$'\033[31m'; VERDE=$'\033[32m'; AMAR=$'\033[33m'
  AZUL=$'\033[34m'; MAGENTA=$'\033[35m'; CIAN=$'\033[36m'
  GRIS=$'\033[90m'; NEGRITA=$'\033[1m'; FIN=$'\033[0m'
else
  ROJO=""; VERDE=""; AMAR=""; AZUL=""; MAGENTA=""; CIAN=""; GRIS=""; NEGRITA=""; FIN=""
fi

mkdir -p "$RAIZ/logs"
PIDS=()
NOMBRES=()

escucha() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# Lanza un servicio en segundo plano. Su salida va al log sin colores y a la
# pantalla con un prefijo de color, línea a línea (awk + fflush: los pipes se
# bufferizan y si no, los logs llegarían a bloques de 4 KB).
arrancar() {
  local nombre="$1" color="$2"; shift 2
  local log="$RAIZ/logs/$nombre.log"
  : > "$log"
  { "$@" 2>&1 | tee -a "$log" \
      | awk -v p="${color}[${nombre}]${FIN} " '{ print p $0; fflush() }'; } &
  PIDS+=("$!")
  NOMBRES+=("$nombre")
  echo "${GRIS}→ $nombre arrancando (log: logs/$nombre.log)${FIN}"
}

limpiar() {
  trap - EXIT; trap '' INT TERM
  echo; echo "${GRIS}Parando servicios…${FIN}"
  local i pid
  for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
    pid="${PIDS[$i]}"
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  # Margen para el apagado ordenado: el lifespan del backend apaga el
  # llama-server, y matarlo a lo bruto dejaría varios GB de RAM ocupados.
  for _ in $(seq 15); do
    local vivos=0
    for pid in "${PIDS[@]}"; do kill -0 "$pid" 2>/dev/null && vivos=1; done
    [ "$vivos" -eq 0 ] && break
    sleep 1
  done
  for pid in "${PIDS[@]}"; do kill -KILL "-$pid" 2>/dev/null || true; done
  echo "${GRIS}Listo.${FIN}"
}
trap 'limpiar; exit 0' INT TERM
trap limpiar EXIT

esperar() {
  local nombre="$1" url="$2" limite="$3" i=0
  while [ "$i" -lt "$limite" ]; do
    if curl -sf --max-time 2 "$url" >/dev/null 2>&1; then
      echo "${VERDE}✓${FIN} $nombre responde"
      return 0
    fi
    kill -0 "${PIDS[${#PIDS[@]}-1]}" 2>/dev/null || true
    sleep 1; i=$((i + 1))
  done
  echo "${AMAR}!${FIN} $nombre no respondió en ${limite}s — revisa sus líneas de arriba"
  return 1
}

# ---------------------------------------------------------------- frontend
if [ "$DEV" -eq 0 ]; then
  if [ ! -f web/dist/index.html ] \
     || [ -n "$(find web/src web/astro.config.mjs web/package.json \
                     -newer web/dist/index.html 2>/dev/null)" ]; then
    echo "${NEGRITA}Compilando el frontend${FIN} ${GRIS}(hay fuentes más nuevas que el build)${FIN}"
    pnpm --dir "$RAIZ/web" build
  else
    echo "${GRIS}Frontend al día, no recompilo.${FIN}"
  fi
fi

# ---------------------------------------------------------------- ComfyUI
if [ "$CON_COMFY" -eq 1 ]; then
  if escucha "$PUERTO_COMFY"; then
    echo "${GRIS}ComfyUI ya escucha en $PUERTO_COMFY, lo reutilizo.${FIN}"
    CON_COMFY=0
  elif [ -x "$COMFY_DIR/venv/bin/python" ]; then
    # Su propio intérprete, no comfy-cli: 'comfy launch' usa el python del shell
    # actual y revienta con ModuleNotFoundError (sqlalchemy y compañía viven en
    # el venv de ComfyUI). main.py acepta los flags del Manager por su cuenta.
    arrancar comfy "$MAGENTA" bash -c \
      "cd '$COMFY_DIR/ComfyUI' && exec '$COMFY_DIR/venv/bin/python' main.py \
       --enable-manager --enable-manager-legacy-ui --gpu-only"
  elif command -v comfy >/dev/null 2>&1; then
    # Sin venv a la vista: que lo intente comfy-cli.
    arrancar comfy "$MAGENTA" \
      comfy launch -- --enable-manager --enable-manager-legacy-ui --gpu-only
  else
    echo "${ROJO}No encuentro ComfyUI${FIN} (ni $COMFY_DIR/venv ni 'comfy' en el PATH)." >&2
    exit 1
  fi
  [ "$CON_COMFY" -eq 1 ] && esperar ComfyUI "http://127.0.0.1:$PUERTO_COMFY/system_stats" 180 || true
fi

# ---------------------------------------------------------------- backend
if escucha "$PUERTO_BACK"; then
  echo "${ROJO}El puerto $PUERTO_BACK ya está ocupado.${FIN} ¿Tienes otro Loomcast abierto?" >&2
  exit 1
fi
arrancar loomcast "$CIAN" \
  env PYTHONUNBUFFERED=1 "$RAIZ/.venv/bin/uvicorn" backend.main:app \
      --host "$HOST" --port "$PUERTO_BACK"
esperar Loomcast "http://127.0.0.1:$PUERTO_BACK/api/salud" 60 || true

# ---------------------------------------------------------------- astro dev
if [ "$DEV" -eq 1 ]; then
  if [ "$HOST" = "0.0.0.0" ]; then
    arrancar web "$AZUL" pnpm --dir "$RAIZ/web" dev --host 0.0.0.0
  else
    arrancar web "$AZUL" pnpm --dir "$RAIZ/web" dev
  fi
  esperar Astro "http://localhost:$PUERTO_WEB/" 60 || true
fi

# ---------------------------------------------------------------- resumen
PUERTO_UI=$PUERTO_BACK
HOST_UI=127.0.0.1
# Astro escucha en localhost (::1), no en 127.0.0.1: con la IP no responde.
if [ "$DEV" -eq 1 ]; then PUERTO_UI=$PUERTO_WEB; HOST_UI=localhost; fi

echo
echo "${NEGRITA}  Loomcast en marcha${FIN}"
echo "  ${GRIS}·${FIN} UI           http://$HOST_UI:$PUERTO_UI"
if [ "$HOST" = "0.0.0.0" ]; then
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  [ -n "$IP" ] && echo "  ${GRIS}·${FIN} desde la red http://$IP:$PUERTO_UI  ${AMAR}(sin contraseña: solo en red de confianza)${FIN}"
fi
echo "  ${GRIS}·${FIN} ComfyUI      http://127.0.0.1:$PUERTO_COMFY"
echo "  ${GRIS}·${FIN} logs         $RAIZ/logs/"

# Sin los parches de MPS la música falla en pistas de más de ~33 s y Qwen-Image-Edit
# revienta en cuanto lleva una referencia. Los dos fallos aparecen a mitad de
# generación, no al arrancar, así que mejor avisar aquí.
if [ -f "$RAIZ/logs/comfy.log" ] && ! grep -q "\[loomcast\] Parche" "$RAIZ/logs/comfy.log"; then
  echo "  ${AMAR}!${FIN} no veo el parche MPS en el arranque de ComfyUI:"
  echo "    ${GRIS}./.venv/bin/python scripts/instalar_parches.py${FIN}"
fi
echo
echo "${GRIS}  Ctrl+C para parar todo.${FIN}"
echo

# Vigilancia: si un servicio se cae, paramos el resto en vez de dejar medio
# sistema en pie fingiendo que funciona.
while true; do
  for i in "${!PIDS[@]}"; do
    if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
      echo "${ROJO}✗ ${NOMBRES[$i]} se ha parado${FIN} — cierro el resto."
      exit 1
    fi
  done
  sleep 2
done
