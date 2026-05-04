# syntax=docker/dockerfile:1.7

# ── Build stage ───────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@10.30.0 --activate

COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/pnpm/store,sharing=locked \
    pnpm config set store-dir /pnpm/store \
    && pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

# ── Production stage ──────────────────────────────────────────────
# nginx:alpine auto-processes /etc/nginx/templates/*.template via envsubst
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 80
