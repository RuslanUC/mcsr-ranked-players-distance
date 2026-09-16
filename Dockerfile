FROM python:3.14-slim-bookworm AS deps

WORKDIR /mcsrpd

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update -y && apt install curl -y
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
COPY pymcsrd-c pymcsrd-c

ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv VIRTUAL_ENV=.venv uv sync --locked --no-dev
RUN --mount=type=cache,target=/root/.cache/uv VIRTUAL_ENV=.venv-dev uv sync --locked --active


FROM python:3.14-slim-bookworm AS compile-graph

ARG APP_TYPE
ENV APP_TYPE=${APP_TYPE}
WORKDIR /mcsrpd

COPY --from=deps /mcsrpd/.venv-dev /mcsrpd/.venv
COPY graph-${APP_TYPE}.pkl compile_graph.py ./

ENV PATH="/mcsrpd/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
RUN python compile_graph.py


FROM python:3.14-slim-bookworm

ARG APP_TYPE
ENV APP_TYPE=${APP_TYPE}
WORKDIR /mcsrpd

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update -y && apt install dumb-init curl -y && apt autoremove && apt clean

COPY app.py app.py
COPY --from=deps /mcsrpd/.venv /mcsrpd/.venv
COPY --from=compile-graph /mcsrpd/graph /mcsrpd/graph

ENV PATH="/mcsrpd/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
