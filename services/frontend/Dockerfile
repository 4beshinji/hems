# Build Stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm@10.30.0 \
    && pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

# Production Stage
# nginx:alpine auto-processes /etc/nginx/templates/*.template via envsubst
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 80
