from serveur import config


def test_les_adresses_du_code_restent_autorisees(monkeypatch):
    monkeypatch.setenv("ORIGINES_ADMIN", "https://console.exemple.app/, http://localhost:5173")
    origines = config.origines_admin()
    assert "https://starpole-web.web.app" in origines
    assert "https://console.exemple.app" in origines
    assert origines.count("http://localhost:5173") == 1


def test_sans_variable(monkeypatch):
    monkeypatch.delenv("ORIGINES_ADMIN", raising=False)
    assert config.origines_admin() == list(config.ORIGINES_ADMIN_DEFAUT)
