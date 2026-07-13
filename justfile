default_session_id := "20c8716c-29c0-59ae-b99a-64810c01ee8f" # uuid5(NAMESPACE_DNS, "reaction-aggregator/demo-session")

default:
    just --list

test:
    docker build --target test -t reaction-aggregator:test --progress=plain .

seed session_id=default_session_id:
    docker compose run --build --rm seed {{session_id}}

run session_id=default_session_id:
    docker compose run --build --rm aggregate {{session_id}}

notebook:
    docker compose up --build jupyter

reset:
    @echo "wiping data/ and re-seeding the default session"
    rm -rf data
    just seed
