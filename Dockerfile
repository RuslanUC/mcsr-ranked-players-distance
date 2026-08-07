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


FROM python:3.14-slim-bookworm AS trim-graph

ARG APP_TYPE
ENV APP_TYPE=${APP_TYPE}
WORKDIR /mcsrpd

COPY --from=deps /mcsrpd/.venv /mcsrpd/.venv
COPY graph-${APP_TYPE}.pkl extract_matches_seasons_from_graph.py ./

ENV PATH="/mcsrpd/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
RUN python extract_matches_seasons_from_graph.py


FROM python:3.14-slim-bookworm

ARG APP_TYPE
ENV APP_TYPE=${APP_TYPE}
WORKDIR /mcsrpd

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update -y && apt install dumb-init curl -y && apt autoremove && apt clean

COPY app.py app.py
COPY --from=deps /mcsrpd/.venv /mcsrpd/.venv
COPY --from=trim-graph /mcsrpd/graph-${APP_TYPE}-trimmed.pkl /mcsrpd/graph-${APP_TYPE}-trimmed.pkl
COPY --from=trim-graph /mcsrpd/matches-${APP_TYPE}.bin /mcsrpd/matches-${APP_TYPE}.bin
COPY --from=trim-graph /mcsrpd/seasons-${APP_TYPE}.bin /mcsrpd/seasons-${APP_TYPE}.bin

ENV PATH="/mcsrpd/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
