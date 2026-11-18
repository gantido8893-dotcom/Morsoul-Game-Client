"""Update manifest: a list of files with SHA-256 hashes, signed with Ed25519.
The server only serves it. The private key never lives on the server."""

import base64
from typing import Annotated

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from morsoul_core.integrity import canonical


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    size: int = Field(ge=0)
    url: str


class UpdateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appVersion: str
    contentVersion: int = Field(ge=1)
    publishedAt: int = Field(ge=0)
    files: list[ManifestFile]


def generate_keypair() -> tuple[bytes, str]:
    """Return (private key as PEM bytes, public key as base64 of the 32 raw bytes)."""
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pem, base64.b64encode(public).decode()


def sign_manifest(manifest: dict, private_pem: bytes) -> str:
    key = serialization.load_pem_private_key(private_pem, password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return base64.b64encode(key.sign(canonical(manifest))).decode()


def verify_manifest(manifest: dict, signature_b64: str, public_b64: str) -> bool:
    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
        public.verify(base64.b64decode(signature_b64), canonical(manifest))
        return True
    except (InvalidSignature, ValueError):
        return False
