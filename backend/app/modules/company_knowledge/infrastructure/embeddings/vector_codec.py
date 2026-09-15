from collections.abc import Sequence

import numpy as np

# Orden de bytes explícito: `np.float32` usa el nativo de la máquina. En
# x86 coincide, pero el formato persistido no debe depender del equipo.
_FLOAT32_LE = np.dtype("<f4")


def vector_to_bytes(values: Sequence[float] | np.ndarray) -> bytes:
    """Serializa `float32` little-endian, plano."""
    return np.asarray(values, dtype=_FLOAT32_LE).tobytes()


def bytes_to_vector(data: bytes) -> np.ndarray:
    """Reconstruye el vector sin copias al cargar el índice."""
    return np.frombuffer(data, dtype=_FLOAT32_LE)


def l2_normalize(values: np.ndarray | Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm > 0.0:
        arr = arr / norm
    return arr
