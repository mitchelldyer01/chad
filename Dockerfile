# Dockerfile
FROM python:3.11-slim

# Install git and build essentials
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directory for models
RUN mkdir -p models

# Command to run the application
CMD ["python", "-m", "src.reviewer"]
