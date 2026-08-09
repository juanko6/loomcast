"""Minimal reproduction: torch.multinomial on MPS returns zero-probability indices.

Run:  python repro_multinomial_mps.py
"""
import torch

TOTAL = 217_000     # categories
TRIALS = 2000


def failure_rate(support: int, device: str) -> tuple[int, list]:
    """Sample from a distribution whose last (TOTAL - support) entries are exactly 0."""
    g = torch.Generator(device=device).manual_seed(0)
    bad, examples = 0, []
    for _ in range(TRIALS):
        logits = torch.full((1, TOTAL), float("-inf"), device=device, dtype=torch.float32)
        logits[:, :support] = torch.randn(1, support, device=device, dtype=torch.float32)
        probs = torch.softmax(logits, dim=-1)          # entries >= support are exactly 0.0
        assert probs[0, support:].sum().item() == 0.0  # the distribution really is zero there
        idx = torch.multinomial(probs, 1, generator=g).item()
        if idx >= support:
            bad += 1
            if len(examples) < 3:
                examples.append((idx, probs[0, idx].item()))
    return bad, examples


for device in ("mps", "cpu"):
    if device == "mps" and not torch.backends.mps.is_available():
        continue
    print(f"\ndevice={device}  ({TOTAL} categories, {TRIALS} draws per row)")
    print(f"{'zeros':>8} {'support':>8} {'sampled outside support':>26}   (index, probability)")
    for support in (TOTAL, 100_000, 64_000, 20_000, 1_000):
        bad, examples = failure_rate(support, device)
        print(f"{TOTAL - support:>8} {support:>8} {bad:>18}/{TRIALS}      {examples}")
