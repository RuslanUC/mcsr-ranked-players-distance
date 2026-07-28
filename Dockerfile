FROM python:3.14-slim-bookworm AS deps

WORKDIR /mcsrpd

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update -y && apt install curl -y
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

ENV UV_NO_DEV=1
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked

FROM python:3.14-slim-bookworm

WORKDIR /mcsrpd

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update -y && apt install dumb-init curl -y && apt autoremove && apt clean

COPY app.py app.py
COPY graph.pkl graph.pkl
COPY --from=deps /mcsrpd/.venv /mcsrpd/.venv

ENV PATH="/mcsrpd/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
