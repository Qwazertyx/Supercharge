# Supercharge — image unique servant l'API et le frontend.
#
# Un seul service, aucune étape manuelle : `docker compose up` depuis un clone
# frais doit suffire (sujet §VII.7).

FROM python:3.12-slim

# Pourquoi 3.12 exactement :
#   qiskit 2.4      publie des roues cp310-abi3  → tout Python ≥ 3.10 convient
#   qiskit-aer 0.17 publie des roues cp39 → cp314
# Plusieurs versions conviendraient donc. On fige une version mûre plutôt que
# la plus récente : le build ne dépend d'aucune compilation depuis les sources,
# et l'image reste reproductible dans le temps.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Les dépendances sont copiées seules d'abord : cette couche ne change que
# lorsque requirements.txt change, et le `pip install` (le plus long) est
# alors réutilisé depuis le cache à chaque modification du code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/   ./backend/
COPY frontend/  ./frontend/
COPY data/      ./data/
COPY scripts/   ./scripts/

# Exécution sans privilèges : rien dans cette application n'a besoin de root.
RUN useradd --create-home --shell /usr/sbin/nologin supercharge \
    && chown -R supercharge:supercharge /app
USER supercharge

EXPOSE 8000

# Sonde de vivacité : `docker compose ps` indique « healthy » quand l'API
# répond réellement, et non simplement quand le conteneur a démarré.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
