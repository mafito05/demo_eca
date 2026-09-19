# Panel de administración servido en el VPS: build de Angular + Nginx.
#
# En desarrollo el panel se sirve con `ng serve` y su proxy (`proxy.conf.json`). En el
# servidor no hay dev-server: Nginx sirve los estáticos ya compilados y reproduce ese mismo
# proxy sobre `/api`. Mantener el proxy (en vez de apuntar el panel al :8000 directamente) es
# deliberado: el navegador ve un único origen, así que no hay preflight de CORS ni una URL de
# API embebida en el bundle que haya que recompilar al cambiar de host.

FROM node:24-alpine AS build

WORKDIR /app

# Las dependencias se copian aparte del código: así una edición de un componente no invalida
# la capa del `npm ci`, que es la cara.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# -----------------------------------------------------------------------------
FROM nginx:1.29-alpine AS serve

# El builder `@angular/build:application` deja los estáticos del navegador en `browser/`.
COPY --from=build /app/dist/admin-web/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
# 127.0.0.1 y no `localhost`: dentro del contenedor `localhost` resuelve primero a `::1`, y
# `listen 80` solo abre el socket IPv4 — el healthcheck fallaba con "connection refused" contra
# un Nginx que servia perfectamente por IPv4.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
