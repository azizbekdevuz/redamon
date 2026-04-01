# RedAmon Agent Dockerfile
# Python-based LangGraph agent with MCP and Neo4j integration

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ripgrep \
    jq \
    make \
    gcc \
    g++ \
    openssh-client \
    unzip \
    wget \
    file \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 LTS + npm (for JS/TS projects) + Claude Code CLI
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g yarn pnpm @anthropic-ai/claude-code

# Install Go 1.22 (for Go projects)
RUN curl -fsSL https://go.dev/dl/go1.22.10.linux-amd64.tar.gz | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:/root/go/bin:${PATH}"

# Install Ruby + Bundler (for Ruby/Rails projects)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ruby ruby-dev \
    && rm -rf /var/lib/apt/lists/* \
    && gem install bundler --no-document

# Install Java 17 JDK + Maven (for Java projects)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    maven \
    && rm -rf /var/lib/apt/lists/*

# Install PHP + Composer (for PHP projects)
RUN apt-get update && apt-get install -y --no-install-recommends \
    php-cli php-xml php-mbstring php-curl php-zip \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

# Install .NET 8 SDK (for C# projects)
RUN apt-get update && apt-get install -y --no-install-recommends libicu-dev && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0 --install-dir /usr/share/dotnet \
    && ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet
ENV DOTNET_ROOT="/usr/share/dotnet"

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the API server
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
