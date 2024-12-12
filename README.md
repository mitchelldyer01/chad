# CHAD (Code Health & Analysis Daemon)

An automated system that reviews GitHub pull requests with a focus on database performance and potential hotspots. The system uses a local LLM to analyze code changes and provide detailed feedback about database-related concerns.

## Features

- 🔄 Automated PR monitoring and review
- 💾 Database performance focused analysis
- 🤖 Local LLM processing (no API costs)
- 📊 Real-time metrics and visualization
- 🐳 Containerized deployment
- 🔍 Detailed performance tracking

## System Requirements

### Minimum Requirements (8GB RAM Systems)
- Docker and Docker Compose
- Git
- 8GB RAM
- 5GB free disk space
- MacOS (including M1/M2), Linux, or Windows with WSL2

### Recommended Models by System:
| RAM Available | Recommended Model | Memory Usage |
|--------------|------------------|---------------|
| 8GB | TinyLlama (1.1B) or Phi-2 (2.7B) | 2-3GB |
| 16GB | Mistral 7B | 4-5GB |

## Quick Start

1. Clone the repository:
```bash
git clone https://github.com/mitchelldyer01/chad
cd chad
```

2. Create environment file:
```bash
cp .env.example .env
```

3. Configure `.env` with your settings:
```env
GITHUB_TOKEN=your_github_token
REPO_PATH=/app/repos/your-repo
REPO_OWNER=your-github-username
REPO_NAME=your-repo-name
MODEL_PATH=/app/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf  # Adjust based on your model choice
CHECK_INTERVAL=300
```

4. Download the appropriate model based on your system:

For 8GB Systems:
```bash
# Option 1: TinyLlama (Recommended for 8GB RAM)
mkdir -p models
curl -L https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

# Option 2: Phi-2
curl -L https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf -o models/phi-2.Q4_K_M.gguf
```

For 16GB Systems:
```bash
# Mistral 7B
curl -L https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf -o models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
```

5. Configure Docker resources in `docker-compose.yml`:

For 8GB Systems:
```yaml
services:
  pr-reviewer:
    deploy:
      resources:
        limits:
          memory: 4G
```

For 16GB Systems:
```yaml
services:
  pr-reviewer:
    deploy:
      resources:
        limits:
          memory: 8G
```

6. Start the service:
```bash
docker compose up --build
```

## Project Structure

```
chad/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── models/          # LLM model storage
├── data/           # SQLite database storage
└── src/
    ├── reviewer.py    # Main PR review logic
    ├── config.py      # Configuration management
    ├── metrics_tui.py # Metrics visualization
    └── utils/
        ├── github.py    # GitHub API interactions
        └── database.py  # Database operations
```

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| GITHUB_TOKEN | GitHub Personal Access Token | Required |
| REPO_PATH | Path to local repo clone | Required |
| REPO_OWNER | GitHub repository owner | Required |
| REPO_NAME | GitHub repository name | Required |
| MODEL_PATH | Path to LLM model file | Required |
| CHECK_INTERVAL | PR check interval (seconds) | 300 |

### Performance Tuning

#### 8GB RAM Systems
```python
llm = Llama(
    model_path=Config.MODEL_PATH,
    n_ctx=512,      # Smaller context window
    n_batch=4,      # Smaller batch size
    n_threads=2     # Fewer threads
)
```

#### 16GB RAM Systems
```python
llm = Llama(
    model_path=Config.MODEL_PATH,
    n_ctx=2048,     # Larger context window
    n_batch=8,      # Larger batch size
    n_threads=4     # More threads
)
```


## Metrics and Monitoring

### Real-time TUI Dashboard

Run the TUI metrics dashboard:

```bash
# Inside the container
docker exec -it pr-reviewer-container python -m src.metrics_tui

# Or locally with direct database access
python -m src.metrics_tui --db-path ./data/pr_tracker.db
```

### Metrics Features

- Real-time updates (default: 5 seconds)
- Historical trend graphs
- PR processing statistics
- Token usage tracking
- Success/failure rates
- Processing time analysis

### TUI Navigation

Arrow keys: Navigate panels
'q': Quit
'h': Show help

## Database Schema
The system uses SQLite with the following main tables:

- processed_prs: Tracks processed pull requests
- review_history: Stores review feedback history
- pr_metrics: Performance metrics per PR
- llm_metrics: LLM usage statistics
- daily_metrics: Aggregated daily statistics

## Development Setup
For local development without Docker:

Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the service:

```bash
python -m src.reviewer
```

## Dependencies

### Core Dependencies

- llama-cpp-python
- GitPython
- requests
- python-dotenv
- sqlite3

### Metrics Dependencies

- textual
- pandas
- asciichartpy

### Development Dependencies

- pytest
- black
- flake8

