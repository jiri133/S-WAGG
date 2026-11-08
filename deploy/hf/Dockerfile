# SolarTriage on Hugging Face Spaces (Docker SDK): one container, FastAPI on port 7860 serves
# the API under /api and the built React app everywhere else (STATIC_DIR).
FROM python:3.12-slim

COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Spaces run the container as user 1000; everything it writes (SQLite, Grad-CAM cache) is in $HOME.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    UV_PYTHON_INSTALL_DIR=/home/user/.uv-python \
    STATIC_DIR=/home/user/app/frontend/dist \
    WEBHOOK_URL=http://127.0.0.1:7860/api/mock/ticketing
WORKDIR /home/user/app
COPY --chown=user . .

# React, built once: FastAPI serves frontend/dist.
RUN cd frontend && npm ci && npm run build
# FastAPI (Python 3.14, ONNX Runtime, torch CPU for Grad-CAM) and the RL planner it calls.
RUN cd backend && uv sync --no-dev --frozen
RUN cd RL && uv sync --no-dev --frozen --python 3.14
# The Raptor crops (15.5 MB, MIT): the simulator builds the drone frames from them.
RUN python -c "import io, urllib.request, zipfile; url = 'https://raw.githubusercontent.com/RaptorMaps/InfraredSolarModules/master/2020-02-14_InfraredSolarModules.zip'; zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read())).extractall('data/raptor')"

EXPOSE 7860
CMD ["sh", "-c", "cd backend && uv run --no-dev fastapi run app/main.py --host 0.0.0.0 --port 7860"]
