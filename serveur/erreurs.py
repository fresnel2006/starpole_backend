import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("starpole")

MESSAGES_HTTP = {
    404: "Ressource introuvable.",
    405: "Méthode non autorisée.",
}


class ErreurApi(Exception):
    """Erreur renvoyée au client avec un message en français."""

    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


def _reponse(statut: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=statut, content={"erreur": message})


def installer_gestionnaires(app: FastAPI) -> None:
    @app.exception_handler(ErreurApi)
    async def _erreur_api(_: Request, erreur: ErreurApi):
        return _reponse(erreur.statut, erreur.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, erreur: RequestValidationError):
        # Seuls les noms des champs sont renvoyés, jamais leurs valeurs.
        champs = []
        for e in erreur.errors():
            nom = str(e["loc"][-1]) if e.get("loc") else "requête"
            if nom not in champs:
                champs.append(nom)
        return _reponse(400, "Requête invalide. Champ(s) incorrect(s) : " + ", ".join(champs) + ".")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, erreur: StarletteHTTPException):
        return _reponse(erreur.status_code, MESSAGES_HTTP.get(erreur.status_code, "Erreur de requête."))

    @app.exception_handler(Exception)
    async def _inattendue(_: Request, erreur: Exception):
        logger.error("Erreur inattendue : %s", type(erreur).__name__)
        return _reponse(500, "Erreur interne du serveur.")
