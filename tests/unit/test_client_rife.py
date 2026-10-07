import subprocess
from pathlib import Path

import pytest

from backend.clients import rife


@pytest.fixture
def instalacion(tmp_path, monkeypatch):
    """Un rife-ncnn-vulkan de mentira dentro de un ROOT temporal."""
    bin_dir = tmp_path / "tools" / "rife"
    (bin_dir / "rife-v4.6").mkdir(parents=True)
    binario = bin_dir / "rife-ncnn-vulkan"
    binario.write_text("")
    monkeypatch.setattr(rife, "ROOT", tmp_path)
    monkeypatch.setattr(rife, "RIFE_BIN", "tools/rife/rife-ncnn-vulkan")
    monkeypatch.setattr(rife, "RIFE_MODELO", "rife-v4.6")
    return binario


class Procesos:
    """Sustituye subprocess.run: ffmpeg extrae/rearma cuadros, RIFE los genera."""

    def __init__(self, cuadros_entrada=4, rife_rc=0):
        self.llamadas, self.cuadros, self.rife_rc = [], cuadros_entrada, rife_rc

    def __call__(self, cmd, **kw):
        self.llamadas.append(cmd)
        if cmd[0] == "ffmpeg" and "-i" in cmd and cmd[-1].endswith("%08d.png") and "-framerate" not in cmd:
            for i in range(self.cuadros):
                (Path(cmd[-1]).parent / f"{i + 1:08d}.png").write_bytes(b"x")
        if cmd[0] == "ffmpeg" and "-framerate" in cmd:
            Path(cmd[-1]).write_bytes(b"video")
        rc = self.rife_rc if cmd[0] != "ffmpeg" else 0
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="fallo de vulkan" if rc else "")


def _n_rife(procesos):
    cmd = next(c for c in procesos.llamadas if c[0] != "ffmpeg")
    return int(cmd[cmd.index("-n") + 1])


def test_binario_inexistente(tmp_path, monkeypatch):
    monkeypatch.setattr(rife, "ROOT", tmp_path)
    with pytest.raises(rife.RifeError, match="No se encontró rife-ncnn-vulkan"):
        rife.interpolar(tmp_path / "a.mp4", tmp_path / "b.mp4", 24, 60)


def test_modelo_inexistente(instalacion, monkeypatch, tmp_path):
    monkeypatch.setattr(rife, "RIFE_MODELO", "otro-modelo")
    with pytest.raises(rife.RifeError, match="modelo RIFE"):
        rife.interpolar(tmp_path / "a.mp4", tmp_path / "b.mp4", 24, 60)


@pytest.mark.parametrize("fps_origen,fps_final,frames,esperado", [
    (12, 60, None, 4 * 5),    # factor por fps
    (24, 30, None, 4 * 2),    # el factor mínimo es x2
    (12, 60, 50, 50),         # `frames` manda sobre el factor
    (12, 60, 2, 4),           # nunca menos cuadros que los de entrada
])
def test_cuadros_de_salida(instalacion, tmp_path, monkeypatch, fps_origen, fps_final, frames, esperado):
    p = Procesos(cuadros_entrada=4)
    monkeypatch.setattr(rife.subprocess, "run", p)
    rife.interpolar(tmp_path / "a.mp4", tmp_path / "b.mp4", fps_origen, fps_final, frames)
    assert _n_rife(p) == esperado
    assert (tmp_path / "b.mp4").read_bytes() == b"video"
    assert str(fps_final) in p.llamadas[-1]


def test_ffmpeg_sin_cuadros(instalacion, tmp_path, monkeypatch):
    monkeypatch.setattr(rife.subprocess, "run", Procesos(cuadros_entrada=0))
    with pytest.raises(rife.RifeError, match="no extrajo cuadros"):
        rife.interpolar(tmp_path / "a.mp4", tmp_path / "b.mp4", 12, 60)


def test_rife_falla(instalacion, tmp_path, monkeypatch):
    monkeypatch.setattr(rife.subprocess, "run", Procesos(rife_rc=1))
    with pytest.raises(rife.RifeError, match="fallo de vulkan"):
        rife.interpolar(tmp_path / "a.mp4", tmp_path / "b.mp4", 12, 60)
    assert not (tmp_path / "b.mp4").exists()
