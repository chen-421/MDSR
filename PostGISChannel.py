from baselutils import fclrprint
from json import load
from psycopg2 import connect, Error as psycopg2_error
from psycopg2.extensions import AsIs
from postgis_sql import OPERATION_DIFF_W_UNION, OPERATION_INTERSECT, OPERATION_MINUS, \
    set_global_geom_type, sqlstr_reset_all_tables, \
    sqlstr_create_gid_geom_table, sqlstr_insert_new_record_to_geom_table, \
    sqlstr_export_geom_table_to_file
from osgeo.ogr import Open as ogr_open
from time import time
from datetime import timedelta
from json import dumps
from collections import OrderedDict

def verify(func):
    '''wrapper function used to verify necessary information
    before doing intersect, union etc operation. '''

    def inner(*args, **kwargs):
        if args[0].pgchannel != args[1].pgchannel:
            print("ERROR: PostGISChannel mismatch")
            return None

        if args[0] == args[1]:
            print("ERROR: Same GeoObject")
            return None

        if args[0].name == args[1].name:
            print("ERROR: Same Name")
            return None
        return func(*args, **kwargs)

    return inner

class PostGISChannel:
    ''' Class defining a PostGIS connection channel,
    holds attributes and communication objcet for SQL (POSTGIS) transmission. '''

    def __init__(self, config_path, verbosity, reset_tables=False):
        ''' Initialize PostGISChannel. '''

        # verbosity for easier debugability
        self.verbosity = verbosity

        # load config file
        try:
            config = load(open(config_path, "r"))
        except Exception as e:
            print("Cannot load configuration file, ERROR: %s" % str(e))
            exit(-1)

        # load config parameters
        try:
            self.dbname             = config["dbname"]
            self.user               = config["user"]
            self.pwd                = config["pwd"]
            self.host               = config["host"]
            self.geom_table_name    = config["geometry_table_name"]
            geo_type                = config["geometry_type"] # "MULTILINESTRING" / "MULTIPOLYGON"
            self.SRID               = config["SRID"]
        except LookupError:
            print("Invalid configuration file")
            exit(-1)

        # establish connection
        try:
            self.connection = connect(dbname=self.dbname,
                                      user=self.user,password=self.pwd,
                                      host=self.host)
            fclrprint('Connection established to %s [%s@%s]'
                      % (self.dbname, self.user, self.host), 'g')
        except psycopg2_error as e:
            print("Unable to connect to the database: %s" % str(e))
            exit(-1)

        # set geometry type
        set_global_geom_type(geo_type)

        # reset tables if requested
        #if reset_tables:
        #    self.reset_all_tables()

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def pgcprint(self, pstr):
        ''' Debug printing method. '''

        if self.verbosity:
            fclrprint(pstr, 'b')

    def reset_all_tables(self):
        ''' Reset all tables (geom, map, contain). '''

        sql_reset_all_tables = sqlstr_reset_all_tables(self.geom_table_name, self.SRID)
        cur = self.connection.cursor()
        cur.execute(sql_reset_all_tables)
        self.pgcprint(cur.query.decode())
        # commit changes
        self.connection.commit()
        fclrprint('Reset tables finished', 'c')

    def export_geom_table_to_file(self, geometry_output_jl):
        ''' Export the geometry file to some json-lines file. '''

        export_sql = sqlstr_export_geom_table_to_file(self.geom_table_name, geometry_output_jl)
        cur = self.connection.cursor()
        cur.execute(export_sql)
        self.pgcprint(cur.query.decode())
        # commit changes
        self.connection.commit()
        fclrprint('Exported geomtery info to file %s' % (geometry_output_jl), 'c')
