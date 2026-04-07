#!/bin/bash

if ! docker info | grep -q "Swarm: active"; then
    docker swarm init
fi

docker service rm $(docker service ls -q) 2>/dev/null || true

docker container prune -f

docker network create -d overlay app_network || true

docker build -t app_stack:latest . --no-cache

docker stack deploy -c docker-compose.yml app_stack

echo "Waiting for services to start..."
sleep 10

docker service ls
echo "Application successfully deployed to Swarm!"