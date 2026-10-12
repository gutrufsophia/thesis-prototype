FROM nginx:1.30-alpine

COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/write-config.sh /docker-entrypoint.d/40-write-config.sh
COPY public/ /usr/share/nginx/html/
RUN chmod +x /docker-entrypoint.d/40-write-config.sh

# Render provides PORT at runtime; this is the fallback for local runs
ENV PORT=10000
EXPOSE 10000
