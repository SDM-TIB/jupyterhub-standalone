# JupyterHub Standalone Plugin

A containerized, multi-user JupyterHub instance with a unified REST API for notebook management. Designed for integration into external applications that need to spawn temporary Jupyter environments and serve notebooks to end users.

## Features

- **Multi-instance guest users**: Configurable pool of temporary `guest0..guestN` users
- **Notebook delivery**: Copy notebooks to user containers on-demand via API
- **Session management**: Track session state across multiple concurrent users
- **Auto-cleanup**: Idle server culling with configurable timeouts and kernel lifecycle management
- **Resource limits**: Per-container CPU, memory, and disk quotas
- **Admin dashboard**: Configure limits and monitor running sessions (port 8080)
- **Unified REST API**: Single port (8080) for all operations

## Prerequisites

### Host Machine

- Docker Engine 20.10+ with Docker Compose 1.29+
- Ports `8000` and `8080` available


## Start

### 1. Configure Environment

Edit `.env`:

```bash
JUPYTERHUB_API_TOKEN=<generate-random-token>
JUPYTERHUB_BASE_URL=/ldmjupyter
JUPYTERNOTEBOOK_URL=http://your-host:8000/ldmjupyter/
JUPYTERHUB_USER=3                    # Max concurrent guest users
JUPYTERHUB_TIMEOUT=180               # Idle timeout (seconds)
JUPYTERHUB_CULLER_MAX_AGE=600        # Max server lifetime (seconds)
JUPYTERHUB_PERCENTAGE_CPU=50         # CPU per container (%)
JUPYTERHUB_MEMORY_LIMIT=1G           # Memory per container
```

### 2. Build and Run

```bash
docker compose up -d --build
```

The service will be available at:
- JupyterHub UI: `http://localhost:8000/ldmjupyter/`
- API + Admin: `http://localhost:8080/`

## API Usage

All endpoints are accessible on port `8080` from the host, or `http://jupyterhub:6000` from other containers on the Docker network.

### List Running Sessions

```bash
curl --location 'http://localhost:8080/session_info' \
--header 'Authorization: Bearer YYY-TOKEN'
```

**Response:**
```json
{
  "session_id": "af2bd02ef6de00c259a419fd4a49e699f8ee3e9725291f38e221830160100f81",
  "user": "guest1",
  "all_sessions": {
    "guest0": "fd7118e4915d288fd78e43495237e14619436c52f185ea6ec98d27462611598e",
    "guest1": "af2bd02ef6de00c259a419fd4a49e699f8ee3e9725291f38e221830160100f81"
  }
}
```

### Admin: Configure Server Limits

```bash
curl --location 'http://localhost:8080/admin' \
  --form 'action="default_setup"' \
  --form 'JUPYTERHUB_TIMEOUT="3600"' \
  --form 'JUPYTERHUB_USER="50"' \
  --form 'JUPYTERHUB_PERCENTAGE_CPU="50"' \
  --form 'JUPYTERHUB_MEMORY_LIMIT="2G"'
```

Changes take effect on next container restart.

### Cleanup Unused Volumes

```bash
curl --location 'http://localhost:8080/cleanup_volumes' \
--header 'Authorization: Bearer YYY-TOKEN'
```

Returns count of removed volumes. Also runs automatically every 60 seconds.

### Running Users

```bash
curl --location 'http://localhost:8080/running_user' \
--header 'Authorization: Bearer YYY-TOKEN'
```

### List Available Notebooks

```bash
curl --location 'http://localhost:8080/list_notebooks' \
--header 'Authorization: Bearer YYY-TOKEN'
```

**Response:**
```json
{
    "notebooks": [
        {
            "modified": "2024-09-11 08:00",
            "name": "CoyPU_communities.ipynb"
        },
        {
            "modified": "2025-09-10 13:14",
            "name": "symboliclearning_kge.ipynb"
        }
    ]
}
```

### Open a Notebook (Get Notebook URL)

```bash
curl --location 'http://localhost:8080/open_notebook/CoyPU_communities.ipynb'
```

**Response:**
```json
{
  "success": true,
  "url": "http://your-host:8000/ldmjupyter/user/guest0/notebooks/CoyPU_communities.ipynb",
  "user": "guest0",
  "existing_session": false
}
```

Use the returned `url` to redirect the user to their notebook.

### Get Free User

```bash
curl --location 'http://localhost:8080/get_user'
```

**Response:**
```json
{
  "user": "guest2"
}
```

Returns `503 Service Unavailable` if no free users are available.

## Architecture & Pre-Conditions

### Internal Architecture

- **Port 8000**: JupyterHub hub interface (internal only)
- **Port 6000** (internal): Unified Flask API + admin UI
- **Port 8080** (host): External proxy to port 6000
- **Network**: `jupyterhub_network` (auto-created by Docker Compose)

### Session Lifecycle

1. User requests `/open_notebook/<name>` → system assigns next free guest user
2. JupyterHub spawns Docker container for that user
3. Notebook file copied from shared volume to user's container
4. User redirected to Jupyter UI; kernel starts automatically
5. Idle-culler monitors kernel activity:
   - If idle for `JUPYTERHUB_TIMEOUT` seconds → mark for culling
   - If total age exceeds `JUPYTERHUB_CULLER_MAX_AGE` seconds → force stop
6. Container and its volume are removed when culled

## Troubleshooting

**Port 8080 unavailable**: Change docker-compose.yml to `"8081:6000"` and update requests.

**No free users**: Wait or increase `JUPYTERHUB_USER` and restart.

**Notebook not found**: Ensure `.ipynb` file exists in `./notebooks/` before building. The volume is copied at container startup.

**Servers not culling after timeout**: Check that `JUPYTERHUB_CULLER_MAX_AGE` is set (not `0`) to force kernel termination.
