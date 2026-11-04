# 1. Use the latest stable base image
FROM python:3.11-slim-bookworm

# 2. Install the system dependencies (required tools)
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Set the working directory
WORKDIR /app

# 4. Copy requirements.txt first (to benefit from the layer cache)
COPY requirements.txt .

# 5. Install dependencies without caching and upgrade pip
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code
COPY . .

# 7. Start the bot
CMD ["python3", "bot.py"]
