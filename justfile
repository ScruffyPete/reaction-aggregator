default:
    just --list

build:
    docker build -t reaction-aggregator .

test:
    docker build --target test -t reaction-aggregator:test --progress=plain .

run session_id="demo-session-1":
    docker build -t reaction-aggregator .
    docker run --rm reaction-aggregator {{session_id}}
