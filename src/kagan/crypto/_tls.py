"""Self-signed TLS certificate generation and loading for local HTTPS."""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_CERT_VALIDITY_DAYS = 365
_STATE_DIR_NAME = "tls"


def _default_tls_dir() -> Path:
    """Return ``~/.local/state/kagan/tls/``, creating it if needed."""
    tls_dir = Path.home() / ".local" / "state" / "kagan" / _STATE_DIR_NAME
    tls_dir.mkdir(parents=True, exist_ok=True)
    return tls_dir


def generate_self_signed_cert(
    host: str = "localhost",
    tls_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Generate a self-signed TLS certificate and private key.

    Uses ECDSA (SECP256R1) for compact keys and fast handshakes.

    Args:
        host: The hostname or IP for the certificate's SAN.
        tls_dir: Directory to write ``cert.pem`` and ``key.pem``.
                 Defaults to ``~/.local/state/kagan/tls/``.

    Returns:
        A ``(cert_path, key_path)`` tuple.
    """
    tls_dir = tls_dir or _default_tls_dir()

    cert_path = tls_dir / "cert.pem"
    key_path = tls_dir / "key.pem"

    private_key = ec.generate_private_key(ec.SECP256R1())

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, f"kagan-{host}"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Kagan Local"),
        ]
    )

    now = datetime.datetime.now(datetime.UTC)
    try:
        host_address = ipaddress.ip_address(host)
    except ValueError:
        san_entries: list[x509.GeneralName] = [x509.DNSName(host)]
    else:
        san_entries = [x509.IPAddress(host_address)]
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        san_entries.append(x509.DNSName("localhost"))
        san_entries.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=_CERT_VALIDITY_DAYS))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(private_key, hashes.SHA256())
    )

    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def ensure_tls_cert(
    host: str = "localhost",
    tls_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Return existing cert/key paths or generate a new self-signed pair.

    Args:
        host: The hostname for the certificate.
        tls_dir: Directory containing ``cert.pem`` and ``key.pem``.

    Returns:
        A ``(cert_path, key_path)`` tuple.
    """
    tls_dir = tls_dir or _default_tls_dir()
    cert_path = tls_dir / "cert.pem"
    key_path = tls_dir / "key.pem"

    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    return generate_self_signed_cert(host, tls_dir)


def cert_fingerprint(cert_path: Path) -> str:
    """Compute the SHA-256 fingerprint of a PEM certificate.

    Args:
        cert_path: Path to the PEM-encoded certificate.

    Returns:
        Hex-encoded SHA-256 digest of the DER-encoded certificate.
    """
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    der = cert.public_bytes(serialization.Encoding.DER)
    return hashlib.sha256(der).hexdigest()
