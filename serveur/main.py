import logging

from fastapi import FastAPI

from . import config, routes_auth, routes_notifications
from .erreurs import installer_gestionnaires

logging.basicConfig(level=logging.INFO)

# Aucun CORS : l'application mobile n'en a pas besoin.
app = FastAPI(title="Serveur StarPole")
installer_gestionnaires(app)
app.include_router(routes_auth.routeur)
app.include_router(routes_notifications.routeur)


@app.get("/sante", tags=["Contrôle"])
def sante():
    """Dit si le serveur est prêt. Ne montre que les NOMS des variables qui manquent."""
    manquantes = config.variables_manquantes()
    return {"pret": not manquantes, "variablesManquantes": manquantes}
