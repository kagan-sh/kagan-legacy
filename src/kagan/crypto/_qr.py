"""QR code generation for device pairing."""

from __future__ import annotations

from urllib.parse import urlencode

import qrcode


def pairing_payload(
    host: str,
    port: int,
    *,
    pubkey: str,
    fingerprint: str | None = None,
    tls: bool = False,
) -> str:
    """Build a ``kagan://`` pairing URI.

    Uses the secure key-exchange flow:
    ``kagan://pair?host=...&port=...&pk=<b64-pubkey>&fp=<cert-sha256>&tls=1``.

    Returns:
        A ``kagan://`` URI string.
    """
    params: dict[str, str | int] = {"host": host, "port": port, "pk": pubkey}
    if fingerprint:
        params["fp"] = fingerprint
    if tls:
        params["tls"] = 1
    return f"kagan://pair?{urlencode(params)}"


def _render_matrix_compact(matrix: list[list[bool]]) -> str:
    """Render a QR matrix using half-block Unicode characters.

    Packs two matrix rows into one terminal line, halving both height
    and width compared to a full-block renderer.
    """
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    lines: list[str] = []
    for i in range(0, rows, 2):
        top = matrix[i]
        bottom = matrix[i + 1] if i + 1 < rows else [False] * cols
        line = ""
        for t, b in zip(top, bottom, strict=False):
            if t and b:
                line += "\u2588"  # \u2588  full block  (both dark)
            elif t:
                line += "\u2580"  # \u2580  upper half  (top dark)
            elif b:
                line += "\u2584"  # \u2584  lower half  (bottom dark)
            else:
                line += " "  #    space        (both light)
        lines.append(line)
    return "\n".join(lines)


def generate_pairing_qr(
    host: str,
    port: int,
    *,
    pubkey: str,
    fingerprint: str | None = None,
    tls: bool = False,
) -> str:
    """Generate a terminal-friendly QR code for pairing.

    Args:
        host: The server hostname or IP address.
        port: The server port number.
        pubkey: URL-safe base64 server public key for key-exchange flow.
        fingerprint: Hex TLS certificate fingerprint.
        tls: Whether the server is using TLS.

    Returns:
        A multi-line string representing the QR code using block characters.
    """
    payload = pairing_payload(
        host,
        port,
        pubkey=pubkey,
        fingerprint=fingerprint,
        tls=tls,
    )
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    return _render_matrix_compact(qr.get_matrix())
