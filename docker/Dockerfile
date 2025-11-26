FROM python:3.11-slim

# Install system dependencies including Node.js, screen, and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bash \
    gcc \
    g++ \
    libmagic1 \
    libmagic-dev \
    git \
    nano \
    iproute2 \
    iputils-ping \
    screen \
    nodejs \
    npm \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -g 1000 esec && \
    useradd -u 1000 -g esec -m -s /bin/bash esec

# Set working directory
WORKDIR /app

# Create directory structure
RUN mkdir -p /data/inbox /data/documents /data/summaries /data/logs && \
    chown -R esec:esec /data

# Copy requirements first for better caching
COPY requirements.txt /app/

# Upgrade pip and install wheel to ensure binary wheels are preferred
RUN pip3 install --upgrade pip wheel

# Install requirements with preference for binary wheels
RUN pip3 install --no-cache-dir --prefer-binary -r requirements.txt

# Copy package.json for web-ui
COPY web-ui/package.json /app/web-ui/
WORKDIR /app/web-ui
RUN npm install

# Back to app root
WORKDIR /app

# Copy application code
COPY --chown=esec:esec . /app

# Install Python subprojects
RUN pip install -e /app/document-processor && \
    pip install -e /app/api-server && \
    pip install -e /app/mcp-server

# Copy startup script
COPY docker/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose ports
EXPOSE 8000
EXPOSE 5173

# Switch to app user
USER esec

# Start with screen session
CMD ["/usr/local/bin/start.sh"]