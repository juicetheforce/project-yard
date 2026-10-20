FROM python:3.12-slim
RUN useradd --system --uid 10001 app && mkdir -p /data && chown app /data
WORKDIR /app
COPY app/ /app/
# The release workflow passes the tag (e.g. v0.6); the page footer shows it.
ARG VERSION=dev
ENV APP_VERSION=$VERSION
USER app
EXPOSE 8087
HEALTHCHECK --interval=1m --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8087/healthz',timeout=3)"
CMD ["python", "-u", "/app/app.py"]
