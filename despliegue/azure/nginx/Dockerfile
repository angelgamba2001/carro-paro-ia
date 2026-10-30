# Proxy de entrada para Azure Container Apps. Los contenedores de la replica
# comparten localhost, por eso aqui se usa 127.0.0.1 y no los nombres del compose.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
