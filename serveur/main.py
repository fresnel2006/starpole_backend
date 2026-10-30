import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, routes_admin, routes_auth, routes_moderation, routes_notifications
from .erreurs import installer_gestionnaires

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Serveur StarPole")
installer_gestionnaires(app)
app.include_router(routes_auth.routeur)
app.include_router(routes_notifications.routeur)
app.include_router(routes_admin.routeur)
app.include_router(routes_moderation.routeur)

# CORS uniquement pour la console web d'administration (l'appli mobile n'en a pas besoin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.origines_admin(),
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/sante", tags=["Contrôle"])
def sante():
    """Dit si le serveur est prêt. Ne montre que les NOMS des variables qui manquent."""
    manquantes = config.variables_manquantes()
    return {"pret": not manquantes, "variablesManquantes": manquantes}
