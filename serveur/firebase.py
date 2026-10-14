import json
import logging
from functools import lru_cache

import firebase_admin
from firebase_admin import credentials, firestore

from . import config
from .depot import DepotFirestore
from .erreurs import ErreurApi

logger = logging.getLogger("starpole")


@lru_cache(maxsize=1)
def application() -> firebase_admin.App:
    try:
        informations = json.loads(config.compte_service_json())
        identifiants = credentials.Certificate(informations)
        return firebase_admin.initialize_app(identifiants)
    except ErreurApi:
        raise
    except Exception as e:
        logger.error("Initialisation de Firebase impossible : %s", type(e).__name__)
        raise ErreurApi(500, "Configuration Firebase invalide.")


@lru_cache(maxsize=1)
def obtenir_db():
    application()
    return firestore.client()


def obtenir_depot() -> DepotFirestore:
    return DepotFirestore(obtenir_db())
