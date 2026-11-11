#!/bin/sh
# One-shot job: create or upgrade Temporal's schema in both of its databases.
# Safe to repeat: setup-schema at version 0.0 only creates the version table if
# it is missing, and update-schema applies only the versions not yet applied.
set -eu

schema_dir=/etc/temporal/schema/postgresql/v12
for target in temporal:temporal temporal_visibility:visibility; do
    db=${target%%:*}
    dir=${target##*:}
    echo "temporal-schema: ${db}"
    temporal-sql-tool --plugin postgres12 --ep db -p 5432 -u temporal --pw "$TEMPORAL_DB_PASSWORD" \
        --db "$db" setup-schema -v 0.0
    temporal-sql-tool --plugin postgres12 --ep db -p 5432 -u temporal --pw "$TEMPORAL_DB_PASSWORD" \
        --db "$db" update-schema -d "${schema_dir}/${dir}/versioned"
done
echo "temporal-schema: done"
