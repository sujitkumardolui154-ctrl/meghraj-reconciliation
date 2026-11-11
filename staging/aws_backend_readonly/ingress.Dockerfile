FROM nginx:1.28-alpine
# A separate, uncredentialed localhost-only ingress for the internal backend.
# The backend remains on its original --internal Docker network.
COPY staging/aws_backend_readonly/ingress.conf.template /etc/nginx/templates/default.conf.template
RUN chmod 0644 /etc/nginx/templates/default.conf.template
ENV NGINX_ENVSUBST_FILTER=^BACKEND_NAME$
USER 10001:10001
EXPOSE 8080
