local use_metadata = os.getenv("OSM2PGSQL_USE_METADATA") == "true"

local tables = {}

local function merge(first, second)
    local result = {}

    for _, v in ipairs(first) do
        table.insert(result, v)
    end

    for _, v in ipairs(second) do
        table.insert(result, v)
    end

    return result
end

local metadata_columns = {
    { column = 'version', type = 'int' },
    { column = 'timestamp', sql_type = 'timestamptz' },
    { column = 'changeset', type = 'bigint' },
    { column = 'uid', type = 'bigint' },
    { column = 'username', type = 'text' },
}
local metadata_indexes = {
    { column = 'timestamp', method = 'btree' },
}

local node_columns = {
    { column = 'tags', type = 'jsonb' },
    { column = 'geom', type = 'point', projection = 4326 }
}
local node_indexes = {
    { column = 'tags', method = 'gin' },
    { column = 'geom', method = 'gist' },
}

local way_columns = {
    { column = 'tags', type = 'jsonb' },
    { column = 'geom', type = 'linestring', projection = 4326 }
}
local way_indexes = {
    { column = 'tags', method = 'gin' },
    { column = 'geom', method = 'gist' },
}

local relation_columns = {
    { column = 'tags', type = 'jsonb' },
    { column = 'members', type = 'jsonb' },
    { column = 'geom', type = 'multipolygon', projection = 4326 }
}
local relation_indexes = {
    { column = 'tags', method = 'gin' },
    { column = 'geom', method = 'gist' },
}

if use_metadata then
    node_columns = merge(metadata_columns, node_columns)
    way_columns = merge(metadata_columns, way_columns)
    relation_columns = merge(metadata_columns, relation_columns)

    node_indexes = merge(metadata_indexes, node_indexes)
    way_indexes = merge(metadata_indexes, way_indexes)
    relation_indexes = merge(metadata_indexes, relation_indexes)
end

tables.nodes = osm2pgsql.define_node_table('nodes', node_columns, { indexes = node_indexes })
tables.ways = osm2pgsql.define_way_table('ways', way_columns, { indexes = way_indexes })
tables.relations = osm2pgsql.define_relation_table('relations', relation_columns, { indexes = relation_indexes })

local function format_dt(ts)
    return os.date('!%Y-%m-%dT%H:%M:%SZ', ts)
end

local function add_metadata(row, object)
    row.version = object.version
    row.timestamp = format_dt(object.timestamp)
    row.changeset = object.changeset
    row.uid = object.uid
    row.username = object.user
end

function osm2pgsql.process_node(object)
    local row = {
        tags = object.tags,
        geom = object:as_point()
    }
    if use_metadata then
        add_metadata(row, object)
    end
    tables.nodes:insert(row)
end


function osm2pgsql.process_way(object)
    local row = {
        tags = object.tags,
        geom = object:as_linestring()
    }
    if use_metadata then
        add_metadata(row, object)
    end
    tables.ways:insert(row)
end


function osm2pgsql.process_relation(object)
    local row = {
        tags = object.tags,
        members = object.members,
        geom = object:as_multipolygon()
    }
    if use_metadata then
        add_metadata(row, object)
    end
    tables.relations:insert(row)
end