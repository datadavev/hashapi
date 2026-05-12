# README for hashapi

This project provides an experimental web interface to a hashstore.

It is implemented as an Apache webserver acting as the proxy to a FastAPI application running under `uvicorn`.

Startup:

Expects:

- ./data/hashstore The hashstore instance
- ./logs Where apache writes its logs
- 

```
docker compose up --build
```
