from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .codes import email_valide, normaliser_email

FORMAT_ID = r"^[A-Za-z0-9_-]{1,150}$"


class DemandeCode(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, valeur: str) -> str:
        valeur = normaliser_email(valeur)
        if not email_valide(valeur):
            raise ValueError("e-mail invalide")
        return valeur


class VerificationCode(DemandeCode):
    code: str = Field(pattern=r"^\d{4}$")
    nom: Optional[str] = Field(default=None, max_length=100)

    @field_validator("nom")
    @classmethod
    def _nom(cls, valeur: Optional[str]) -> Optional[str]:
        valeur = (valeur or "").strip()
        return valeur or None


class DemandeAppel(BaseModel):
    appelId: str = Field(pattern=FORMAT_ID)


class DemandeMessage(BaseModel):
    conversationId: str = Field(pattern=FORMAT_ID)


class DemandeModeration(BaseModel):
    motif: str = Field(max_length=300)

    @field_validator("motif")
    @classmethod
    def _motif(cls, valeur: str) -> str:
        valeur = valeur.strip()
        if len(valeur) < 3:
            raise ValueError("motif trop court")
        return valeur


class DemandeVerificationAlerte(BaseModel):
    alerteId: str = Field(pattern=FORMAT_ID)


class DemandeAlerte(BaseModel):
    alerteId: str = Field(pattern=FORMAT_ID)
    rayonMetres: float = Field(default=500, gt=0, le=50_000)
