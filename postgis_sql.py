# -*- coding: utf-8 -*-

from os.path import abspath
from psycopg2.extensions import AsIs

OPERATION_INTERSECT = 'ST_INTERSECTION'
OPERATION_MINUS = 'ST_DIFFERENCE'
OPERATION_DIFF_W_UNION = 'INTERNAL_DIFF_W_UNION'

def set_global_geom_type(geo_type='geometry'):
    ''' Set the global type of geometry '''

    global g_geo_type
    g_geo_type = geo_type

def sqlstr_reset_all_tables(geom_tablename, srid):
    ''' Get SQL string to reset tables (geom). '''

    global g_geo_type

    sql_str = '''
        DROP TABLE IF EXISTS %s;
        CREATE TABLE %s (
            gid SERIAL NOT NULL PRIMARY KEY,
            wkt TEXT,
            geo_type VARCHAR(64),
            geo_size REAL,
            ob_name VARCHAR(64),
            ob_type INT
        );
        SELECT AddGeometryColumn('%s', 'geom', %s, '%s', 2);
        ''' % (AsIs(geom_tablename), AsIs(geom_tablename), AsIs(geom_tablename), srid, g_geo_type)
    return sql_str

# def sqlstr_op_records(operation, geom_tablename, segment_1_gid, list_of_gids, buffer_size):
#     ''' Get SQL string to perform operation 'op' between two records . '''
#
#     global g_geo_type
#
#     sub_op = operation
#     if operation == OPERATION_DIFF_W_UNION:
#         sub_op = OPERATION_MINUS
#
#     sql_str = '''
#             INSERT INTO %s (wkt, geom, geo_type, geo_size, ob_name, ob_type)
#             SELECT ST_ASTEXT(res.lr), lr, %s, ST_AREA(lr), %s, %s
#             FROM(
#                 SELECT ST_MULTI( ''' % (AsIs(geom_tablename), AsIs(g_geo_type), AsIs(''), AsIs(0))
#
#     if g_geo_type == 'MULTILINESTRING':
#         sql_str += '''
#                     ST_INTERSECTION(
#                         l.geom,
#                         %s(
#                             st_buffer(l.geom, %s),
#                             st_buffer(r.geom, %s)
#                         )
#                     )
#             ''' % (sub_op, buffer_size, buffer_size)
#     else:
#         sql_str += '''
#                     %s(
#                         st_buffer(l.geom, 0),
#                         st_buffer(r.geom, 0)
#                     )
#             ''' % (sub_op)
#
#     sql_str += '''
#                 ) as lr
#                 FROM (
#                     SELECT geom
#                     FROM %s
#                     WHERE %s.gid = %s
#                 ) as l, ''' % (AsIs(geom_tablename), AsIs(geom_tablename), segment_1_gid)
#
#     gid_2_sql_substring = sqlstr_build_or_clause_of_gids(geom_tablename, list_of_gids)
#
#     if operation == OPERATION_DIFF_W_UNION:
#         sql_str += '''
#             (
#                 SELECT ST_Multi(ST_Union(f.geom)) as geom
#                 FROM (
#                     SELECT geom
#                     FROM %s
#                     WHERE %s
#                 ) as f
#             ) as r
#         ''' % (AsIs(geom_tablename), gid_2_sql_substring)
#     else:
#         sql_str += '''
#             (
#                 SELECT geom
#                 FROM %s
#                 WHERE %s
#             ) as r
#         ''' % (AsIs(geom_tablename), gid_2_sql_substring)
#
#     st_geo_type = 'ST_MultiLineString'
#     if g_geo_type != 'MULTILINESTRING':
#         st_geo_type = 'ST_MultiPolygon'
#
#     sql_str += '''
#         ) res
#         where ST_geometrytype(res.lr) = '%s'
#         RETURNING gid
#     ''' % (st_geo_type)
#
#     return sql_str

def sqlstr_create_gid_geom_table(active_tablename, srid,startId):
    ''' Create a table with gid, geom data. '''

    sql_str = '''
        DROP TABLE IF EXISTS %s; 
        DROP SEQUENCE IF EXISTS %s_gid_seq; 
       
        CREATE TABLE %s (
            gid SERIAL NOT NULL PRIMARY KEY,
            wkt TEXT,
            geo_type VARCHAR(64),  -- 支持更长的几何类型名称
            geo_area REAL,
            geo_length REAL,
            ob_name VARCHAR(256),
            ob_type VARCHAR(64),
            filename TEXT,
            osm_id VARCHAR(64),
            en_xmin REAL,
            en_xmax REAL,
            en_ymin REAL,
            en_ymax REAL
        );
        SELECT AddGeometryColumn('%s', 'geom', %s, 'geometry', 2);  -- 使用通用几何类型
        ALTER SEQUENCE %s_gid_seq RESTART WITH %s;
        ''' % (AsIs(active_tablename),AsIs(active_tablename),
               AsIs(active_tablename),
               AsIs(active_tablename), srid,
               AsIs(active_tablename), startId)
    return sql_str
def sqlstr_insert_new_record_to_geom_table(geom_tablename, active_tablename, geo_type='MULTILINESTRING', ob_name='', ob_type=0):
    ''' Insert a new record into the geometry table with additional fields. '''

    sql_str = '''
        INSERT INTO %s (wkt, geom, geo_type,  geo_area, geo_length, ob_name, ob_type, filename, osm_id,en_xmin,en_xmax,en_ymin,en_ymax)
        SELECT wkt, geom, geo_type,  geo_area, geo_length, ob_name, ob_type, filename, osm_id,en_xmin,en_xmax,en_ymin,en_ymax
        FROM %s
        RETURNING gid;
    ''' % (AsIs(geom_tablename), AsIs(active_tablename))
    return sql_str

def sqlstr_build_or_clause_of_gids(geom_tablename, list_of_gids):
    ''' Union (clause) of gids from a list of gid/gids. '''

    sql_substr = ""
    for gid_idx, gid_val in enumerate(list_of_gids):
        if gid_idx > 0:
            sql_substr += ' or'
        sql_substr +=  ' %s.gid = %s' % (AsIs(geom_tablename), gid_val)
    return sql_substr

def sqlstr_export_geom_table_to_file(geom_tablename, jl_filename):
    ''' Get SQL commaind for exporting the geometry file to some json-lines file. '''

    sql_str = '''
        COPY (SELECT ROW_TO_JSON(t) FROM (SELECT * FROM %s) t) TO '%s'
        ''' % (AsIs(geom_tablename), abspath(jl_filename))
    return sql_str


def sqlstr_insert_relation(rel_tablename):
    ''' SQL for inserting a new relationship '''
    sql_str = '''
        INSERT INTO %s (from_gid, to_gid, topology, normalized_distance,distance, overlapping_area, sem_text, spatialweight,direction)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING rid;
    ''' % (AsIs(rel_tablename))
    return sql_str