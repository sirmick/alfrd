FROM python:3.11-alpine

# Install system dependencies
RUN apk add --no-cache \
    supervisor \
    curl \
    bash \
    gcc \
    musl-dev \
    libffi-dev \
    libmagic

# Create app user
RUN addgroup -g 1000 esec && \
    adduser -D -u 1000 -G esec esec

# Set working directory
WORKDIR /app

# Create directory structure
RUN mkdir -p /data/inbox /data/documents /data/summaries /data/logs && \
    chown -R esec:esec /data

# Copy requirements first for better caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=esec:esec . /app

# Install each subproject
RUN pip install -e /app/document-processor && \
    pip install -e /app/api-server && \
    pip install -e /app/mcp-server

# Copy supervisor config
COPY docker/supervisord.conf /etc/supervisord.conf

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose ports
EXPOSE 8000  # API Server
EXPOSE 8080  # Web UI (dev mode)
EXPOSE 3000  # MCP Server

# Switch to app user
USER esec

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]