local tables = {}

tables.nodes = osm2pgsql.define_node_table('nodes', {
    { column = 'version', type = 'int' },
    { column = 'timestamp', type = 'text' },
    { column = 'changeset', type = 'bigint' },
    { column = 'uid', type = 'bigint' },
    { column = 'username', type = 'text' },
    { column = 'tags', type = 'hstore' },
    { column = 'geom', type = 'point', projection = 4326 }
})

tables.ways = osm2pgsql.define_way_table('ways', {
    { column = 'version', type = 'int' },
    { column = 'timestamp', type = 'text' },
    { column = 'changeset', type = 'bigint' },
    { column = 'uid', type = 'bigint' },
    { column = 'username', type = 'text' },
    { column = 'tags', type = 'hstore' },
    { column = 'geom', type = 'linestring', projection = 4326 }
})

tables.relations = osm2pgsql.define_relation_table('relations', {
    { column = 'version', type = 'int' },
    { column = 'timestamp', type = 'text' },
    { column = 'changeset', type = 'bigint' },
    { column = 'uid', type = 'bigint' },
    { column = 'username', type = 'text' },
    { column = 'tags', type = 'hstore' },
    { column = 'members', type = 'jsonb' },
    { column = 'geom', type = 'multipolygon', projection = 4326 }
})

function osm2pgsql.process_node(object)
    tables.nodes:insert({
        version = object.version,
        timestamp = object.timestamp,
        changeset = object.changeset,
        uid = object.uid,
        username = object.user,
        tags = object.tags,
        geom = object:as_point()
    })
end


function osm2pgsql.process_way(object)
    tables.ways:insert({
        version = object.version,
        timestamp = object.timestamp,
        changeset = object.changeset,
        uid = object.uid,
        username = object.user,
        tags = object.tags,
        geom = object:as_linestring()
    })
end


function osm2pgsql.process_relation(object)
    tables.relations:insert({
        version = object.version,
        timestamp = object.timestamp,
        changeset = object.changeset,
        uid = object.uid,
        username = object.user,
        tags = object.tags,
        members = object.members,
        geom = object:as_multipolygon()
    })
end