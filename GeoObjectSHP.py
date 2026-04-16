# -*- coding: utf-8 -*-
import math
import os
from os import listdir
from baselutils import fclrprint
from osgeo import osr, ogr
from osgeo.ogr import Open as ogr_open
from time import time
from datetime import timedelta
from json import dumps
from collections import OrderedDict

from psycopg2._psycopg import AsIs

from Matrixs import SpatialWeightMatrix
from rtree import index
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from shapely.strtree import STRtree
from shapely.wkt import loads as wkt_loads

from PostGISChannel import PostGISChannel
from postgis_sql import sqlstr_create_gid_geom_table, sqlstr_insert_new_record_to_geom_table, set_global_geom_type

#语义模板
SEMANTIC_TEMPLATES = {
    'contains': "{feature1}是{feature2}的一部分",
    'within': "{feature1}位于{feature2}内",
    'intersects': "{feature1}与{feature2}相交",
    'touches': "{feature1}与{feature2}相邻",
    'adjacent': "{feature1}毗邻{feature2}",
    'overlaps': "{feature1}与{feature2}部分重叠",
    'crosses': "{feature1}穿过{feature2}"
}
FUNCTIONAL_RELATIONS = {
    ('water', 'park'): "景观水体",
    ('park', 'water'): "景观水体",
    ('water', 'farm'): "灌溉水源",
    ('farm', 'water'): "灌溉水源",
    ('water', 'water_works'): "设备使用水源",
    ('water_works', 'water'): "设备使用水源",
    ('forest', 'park'): "绿化区域",
    ('park', 'forest'): "绿化区域",
    ('museum', 'attraction'): "景点",
    ('attraction', 'museum'): "景点"
}

class GeoObject:
    ''' Class representing a single geographic feature (e.g., polygon, linestring) '''

    def __init__(self, gid, osm_id, name,geo_type, entity_type,wkt,area,length,xmin,xmax,ymin,ymax,file ):
        ''' Initialize GeoObject. '''
        self.gid = gid                  # 数据库id
        self.osm_id = osm_id            # osm osm_id
        self.name = name                # osm name
        self.geo_type = geo_type        # osm Shape
        self.entity_type = entity_type  # osm fclass
        self.geo_wkt = wkt              # 几何信息wkt
        self.area = area                # 几何计算-面积
        self.length = length            # 几何计算-长度
        self.xmin = xmin                # 定位-xmin
        self.xmax = xmax                # 定位-xmax
        self.ymin = ymin                # 定位-ymin
        self.ymax = ymax                # 定位-ymax
        self.file = file                # osm file

    def __repr__(self):
        ''' Print string for GeoObject class. '''
        return 'gid: %s, name: %s, geo_type: %s, entity_type: %s' \
            % (
             self.gid, self.name, self.geo_type, self.entity_type )

    @classmethod
    def from_shp(cls, pg_channel_obj,path):
        ''' Create GeoObject instances from SHP file. Each geometry is treated as a separate entity. '''
        start_time = time()

        # 生成临时表active_geo_obj
        cur = pg_channel_obj.connection.cursor()
        #序列id初始值
        cur.execute('''SELECT COALESCE(MAX(gid), 0) FROM %s;''', (AsIs(pg_channel_obj.geom_table_name),))
        max_id = cur.fetchone()[0]
        startId = max_id + 1  # 新ID从当前最大值+1开始
        working_object_table_name = 'active_geo_obj'
        sql_create_table = sqlstr_create_gid_geom_table(working_object_table_name, pg_channel_obj.SRID,startId)

        cur.execute(sql_create_table)
        pg_channel_obj.pgcprint(cur.query.decode())

        # Load SHP file
        shp_datasource = ogr_open(path)
        geo_objects = []  # 用于存储生成的 GeoObject 实例

        try:
            layer = shp_datasource.GetLayer(0)
            # 如果没有定义CRS，无法保证单位准确性
            source_srs = layer.GetSpatialRef()
            if source_srs is None:
                raise Exception("警告：数据没有定义坐标系统，无法保证面积单位准确性")

            for feature in layer:
                geometry = feature.GetGeometryRef()

                if not geometry.IsValid():  # 检查几何对象是否有效
                    # 如果几何无效，尝试修复
                    geometry = geometry.MakeValid()
                    if not geometry.IsValid():  # 再次检查修复后的几何是否有效
                        continue  # 如果仍然无效，跳过该几何

                osm_id = feature.GetField("osm_id")
                name = feature.GetField("name")
                # 获取几何类型
                geo_type = geometry.GetGeometryName()  # 例如：'POLYGON', 'MULTIPOLYGON', 'LINESTRING', 等

                # 获取 class 属性 ，可选
                entity_type = feature.GetField("fclass")  # 动态读取

                # 检查 osm_id 是否已经存在
                cur.execute('SELECT 1 FROM %s WHERE osm_id = %s LIMIT 1', (AsIs(pg_channel_obj.geom_table_name), osm_id))
                if cur.fetchone():
                    continue  # 如果osm_id已存在，跳过

                # 插入几何对象到 PostGIS
                # 转换坐标系
                if source_srs.IsGeographic():# 如果是地理坐标系(经纬度)，需要投影转换
                    # 创建目标投影(Web墨卡托，EPSG:3857)
                    target_srs = osr.SpatialReference()
                    target_srs.ImportFromEPSG(3857)
                    # 创建坐标转换
                    transform = osr.CoordinateTransformation(source_srs, target_srs)
                    # 转换坐标系
                    geometry.Transform(transform)
                # 获取几何对象的边界框
                envelope = geometry.GetEnvelope()
                xmin, xmax, ymin, ymax = envelope
                wkt = geometry.ExportToWkt()
                cur.execute('''
                                    INSERT INTO %s (wkt, geom, geo_type, geo_area,geo_length, ob_name, ob_type,filename,osm_id,en_xmin,en_xmax,en_ymin,en_ymax)
                                    VALUES (%s, ST_MakeValid(ST_GeometryFromText(%s, %s)), %s, ST_AREA(ST_GeometryFromText(%s, %s)),ST_LENGTH(ST_GeometryFromText(%s, %s)), %s, %s,%s, %s, %s, %s, %s, %s)
                                    RETURNING gid,geo_area,geo_length;
                                ''', (
                    AsIs(working_object_table_name), wkt, wkt, pg_channel_obj.SRID, geo_type, wkt, pg_channel_obj.SRID,wkt, pg_channel_obj.SRID,
                    name,entity_type,path,osm_id,xmin,xmax,ymin,ymax))

                fetchall = cur.fetchall()
                if len(fetchall) != 1:
                    raise ValueError("Fetched zero or more entries (should be exactly 1): fetchall: %s " % (fetchall))
                gid = fetchall[0][0]

                # 获取几何对象的计算
                length = fetchall[0][1] # 折线长度
                area = fetchall[0][2] # 面的面积
                # if geo_type in ['POLYGON', 'MULTIPOLYGON']:
                #     if source_srs.IsGeographic():# 如果是地理坐标系(经纬度)，需要投影转换
                #         # 创建目标投影(Web墨卡托，EPSG:3857)
                #         target_srs = osr.SpatialReference()
                #         target_srs.ImportFromEPSG(3857)
                #         # 创建坐标转换
                #         transform = osr.CoordinateTransformation(source_srs, target_srs)
                #         # 转换坐标系
                #         geometry.Transform(transform)
                #         # 获取数据
                #         wkt = geometry.ExportToWkt()
                #         area = geometry.GetArea()
                #     elif source_srs.IsProjected(): # 如果是投影坐标系，检查单位并转换
                #         linear_units = source_srs.GetLinearUnits()
                #         unit_name = source_srs.GetLinearUnitsName().lower()
                #         # 常见非米单位转换因子
                #         unit_factors = {
                #             'foot': 0.3048,  # 国际英尺
                #             'feet': 0.3048,  # 国际英尺
                #             'us survey foot': 0.304800609601,  # 美国测量英尺
                #             'metre': 1.0,  # 米
                #             'meter': 1.0,  # 米
                #             'kilometre': 1000.0,  # 千米
                #             'kilometer': 1000.0  # 千米
                #         }
                #         # 获取转换因子
                #         factor = unit_factors.get(unit_name, 1.0)
                #         conversion_factor = factor ** 2  # 面积是长度的平方
                #         # 获取数据
                #         area = geometry.GetArea() * conversion_factor
                #         wkt = geometry.ExportToWkt()
                # elif geo_type in ['LINESTRING']:# 针对折线（道路）几何的处理
                #     if source_srs.IsGeographic():  # 如果是地理坐标系(经纬度)，需要投影转换
                #         target_srs = osr.SpatialReference()
                #         target_srs.ImportFromEPSG(3857)  # Web墨卡托投影
                #         transform = osr.CoordinateTransformation(source_srs, target_srs)
                #         geometry.Transform(transform)
                #     wkt = geometry.ExportToWkt()  # 导出为WKT格式
                #     length = geometry.Length()  # 计算折线长度

                # 创建 GeoObject 实例并添加到列表中
                geo_obj = cls(gid,osm_id, name,geo_type,entity_type,wkt,area,length,xmin,xmax,ymin,ymax,path)
                geo_objects.append( geo_obj)  # 存储 FID 和对应的 geo_obj

            # 将数据插入主表
            sql_insert_new_object = sqlstr_insert_new_record_to_geom_table(pg_channel_obj.geom_table_name,
                                                                           working_object_table_name)
            cur.execute(sql_insert_new_object)


            pg_channel_obj.pgcprint(cur.query.decode())

            # 删除临时表
            cur.execute('DROP TABLE %s' % (AsIs(working_object_table_name)))
            pg_channel_obj.pgcprint(cur.query.decode())

            # 提交更改
            pg_channel_obj.connection.commit()
            fclrprint('Created %d geometries from %s' % (len(geo_objects), path), 'c')

            return geo_objects

        finally:
            shp_datasource.Destroy()  # 显式关闭
class RelObject:
    ''' Class representing a single relationship '''

    def __init__(self, rid, geo_object1,geo_object2,topology,normalized_distance,distance,overlapping_area,sem,direction):
        ''' Initialize GeoObject. '''
        self.rid = rid                  # relation id
        self.geo_object1 = geo_object1  # geo_object1
        self.geo_object2 = geo_object2  # geo_object2
        self.topology = topology        #拓扑
        self.normalized_distance = normalized_distance #标准化距离
        self.distance = distance        #距离
        self.overlapping_area = overlapping_area  #重叠面积
        self.direction = direction      #方位
        self.sem = sem                  #语义描述
        self.spatialweight=0.0          #权重


    def __repr__(self):
        ''' Print string for GeoObject class. '''

        return 'rgi: %s,geo1: %s,geo2: %s, topology: %s, distance: %s, overlapping_area: %s, sem: %s' \
            % (  self.rid, self.geo_object1.gid,self.geo_object2.gid,
                 self.topology,self.distance,self.overlapping_area,self.sem )

class GeoObjectsGraph:
    ''' Class representing the geographic objects graph. '''
    MAX_RELATION_DISTANCE = 1000  # 单位：米，超过此距离不建立关系
    UNIT_DISTANCE = 2000  # 单位：米，对此范围内的地理实体进行关系计算
    def __init__(self, pg_channel_object):
        ''' Initialize graph. '''
        self.pgchannel = pg_channel_object
        self.geo_objects = list()  # 存储所有地理对象
        self.relations = list()  # 存储所有关系
        self.spatial_weight_matrix = SpatialWeightMatrix()

    def __repr__(self):
        ''' Print geographic objects and relations in graph. '''

        repr_str = 'GeoObjects:\n'
        for geo_obj in self.geo_objects:
            repr_str += str(geo_obj) + '\n'

        repr_str += '\nRelations:\n'
        for rel in self.relations:
            repr_str += f"({rel['polygon1'].gid}, {rel['relation']}, {rel['polygon2'].gid}, distance: {rel['distance']}, overlappingarea: {rel['overlappingarea']})\n"

        return repr_str

    def export_geom_jl_file(self, geom_outputfile):
        ''' Export geometry mapping file to json-lines file '''

        with open(geom_outputfile, 'w') as write_file:
            for geo_obj in self.geo_objects:
                line_dict = OrderedDict()
                line_dict['gid'] = geo_obj.gid
                line_dict['wkt'] = geo_obj.geo_wkt

                write_file.write(dumps(line_dict) + '\n')
        fclrprint('Exported geographic objects info to file %s' % (geom_outputfile), 'c')
    def export_objects_jl_file(self, objects_outputfile):
        ''' Export geographic objects list to json-lines file '''

        with open(objects_outputfile, 'w') as write_file:
            for geo_obj in self.geo_objects:
                line_dict = OrderedDict()
                line_dict['gid'] = geo_obj.gid
                line_dict['osm_id'] = geo_obj.osm_id
                line_dict['name'] = geo_obj.name
                line_dict['geo_type'] = geo_obj.geo_type
                line_dict['entity_type'] = geo_obj.entity_type
                line_dict['length'] = geo_obj.length
                line_dict['area'] = geo_obj.area
                line_dict['file'] = geo_obj.file

                write_file.write(dumps(line_dict) + '\n')
        fclrprint('Exported geographic objects info to file %s' % (objects_outputfile), 'c')
    def export_relations_jl_file(self, rel_outputfile):
        ''' Export relations list to json-lines file. '''

        with open(rel_outputfile, 'w') as write_file:

            for rel in self.relations:
                line_dict = OrderedDict()
                line_dict['polygon1_osm_id'] = rel.geo_object1.osm_id
                line_dict['polygon2_osm_id'] = rel.geo_object2.osm_id
                line_dict['topology'] = rel.topology
                line_dict['normalized_distance'] = rel.normalized_distance
                line_dict['distance'] = rel.distance
                line_dict['overlapping_area'] = rel.overlapping_area
                line_dict['direction'] = rel.direction
                line_dict['sem'] = rel.sem
                line_dict['spatialweight'] = rel.spatialweight

                write_file.write(dumps(line_dict) + '\n')
        fclrprint('Exported relations info to file %s' % (rel_outputfile), 'c')


    def add_geo_object_to_graph(self, geo_object):
        ''' Add geographic object to the graph. '''

        # 添加新的地理对象
        self.geo_objects.append(geo_object)

        cur = self.pgchannel.connection.cursor()
        try:
            # 从数据库中查询当前对象周围 UNIT_DISTANCE 米范围内的对象
            cur.execute('''
                SELECT gid, osm_id, ob_name, geo_type, ob_type, 
                       wkt, geo_area, geo_length,
                       en_xmin, en_xmax, en_ymin, en_ymax, filename
                FROM %s
                WHERE gid > %s  -- 排除自身
                 -- 先用边界框快速过滤
                AND (en_xmin BETWEEN %s - %s AND %s + %s OR en_xmax BETWEEN %s - %s AND %s + %s)
                AND (en_ymin BETWEEN %s - %s AND %s + %s OR en_ymax BETWEEN %s - %s AND %s + %s)
            ''', (
                AsIs(self.pgchannel.geom_table_name),
                geo_object.gid,
                geo_object.xmin, self.UNIT_DISTANCE, geo_object.xmax, self.UNIT_DISTANCE,
                geo_object.xmin, self.UNIT_DISTANCE, geo_object.xmax, self.UNIT_DISTANCE,
                geo_object.ymin, self.UNIT_DISTANCE, geo_object.ymax, self.UNIT_DISTANCE,
                geo_object.ymin, self.UNIT_DISTANCE, geo_object.ymax, self.UNIT_DISTANCE
            ))
            # 获取附近对象并计算关系
            for row in cur.fetchall():
                existing_obj = GeoObject(
                    gid=row[0], osm_id=row[1], name=row[2],
                    geo_type=row[3], entity_type=row[4], wkt=row[5],
                    area=row[6], length=row[7],
                    xmin=row[8], xmax=row[9], ymin=row[10], ymax=row[11],
                    file=row[12]
                )

                # 计算关系
                rel,_ = self.calculate_relation(cur,geo_object,existing_obj)
                if rel:
                    # 存储关系到数据库
                    #rid = self.store_relation_to_db(cur,rel)
                    #if rid is not None:
                    self.relations.append(rel)

        except Exception as e:
            fclrprint(f"计算空间关系失败: {str(e)}", 'r')
        finally:
            cur.close()

        fclrprint('Add geographic object %s, now object:%s and relation: %s' % (geo_object.gid, str(len(self.geo_objects)),str(len(self.relations))), 'c')

    def store_relation_to_db(self, cur,rel_obj):
        """将关系对象存储到数据库"""
        try:
            # 检查 rela_tbl 表中是否已存在相同的关系数据
            cur.execute('''
                SELECT COUNT(*) FROM rela_tbl
                WHERE from_gid = %s AND to_gid = %s;
            ''', (
                rel_obj.geo_object1.gid,
                rel_obj.geo_object2.gid
            ))

            relation_count = cur.fetchone()[0]
            if relation_count > 0:
                fclrprint(
                    f"空间关系表中已经存在相同的关系数据: from_gid = {rel_obj.geo_object1.gid}, to_gid = {rel_obj.geo_object2.gid}, topology = {rel_obj.topology}",
                    'r')
                return None

            # 将语义描述转换为JSON字符串
            sem_text = dumps(rel_obj.sem, ensure_ascii=False)

            cur.execute('''
                INSERT INTO rela_tbl 
                (from_gid, to_gid, topology, normalized_distance,distance, overlapping_area, sem_text, spatialweight,direction)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING rid;
            ''', (
                rel_obj.geo_object1.gid,
                rel_obj.geo_object2.gid,
                rel_obj.topology,
                rel_obj.normalized_distance,
                rel_obj.distance,
                rel_obj.overlapping_area,
                sem_text,
                rel_obj.spatialweight,
                rel_obj.direction
            ))

            # 获取数据库生成的rid并更新关系对象
            rid = cur.fetchone()[0]
            rel_obj.rid = rid

            self.pgchannel.connection.commit()
            return rid
        except Exception as e:
            self.pgchannel.connection.rollback()
            fclrprint(f"存储关系到数据库失败: {str(e)}", 'r')
            return None

    def batch_store_relations(self):
        """批量存储关系到数据库"""
        if not self.relations:
            return
        if len(self.relations)==0:
            return
        cur = self.pgchannel.connection.cursor()
        try:
            # 准备批量插入数据
            values = []
            for rel in self.relations:
                sem_text = dumps(rel.sem, ensure_ascii=False)
                values.append((
                    rel.geo_object1.gid,
                    rel.geo_object2.gid,
                    rel.topology,
                    rel.normalized_distance,
                    rel.distance,
                    rel.overlapping_area,
                    sem_text,
                    rel.spatialweight,
                    rel.direction
                ))

            # 执行批量插入
            cur.executemany('''
                INSERT INTO rela_tbl (from_gid, to_gid, topology, normalized_distance,distance, overlapping_area, sem_text, 
                spatialweight,direction)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING rid;
            ''', values)

            # 获取生成的rid并更新关系对象
            # rids = [row[0] for row in cur.fetchall()]
            # for rel, rid in zip(relations, rids):
            #     rel.rid = rid

            self.pgchannel.connection.commit()
            return True
        except Exception as e:
            self.pgchannel.connection.rollback()
            fclrprint(f"批量存储关系失败: {str(e)}", 'r')
            return False
        finally:
            cur.close()
    def calculate_relation(self, cur,polygon1, polygon2):
        ''' Calculate topology , distance, and overlapping area between two polygons, and store the relation. '''

        # 计算拓扑关系、距离和重叠面积
        cur.execute('''
            SELECT
                CASE
                    WHEN ST_Contains(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'contains'
                    WHEN ST_Covers(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'covers'
                    WHEN ST_Within(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'within'
                    WHEN ST_Crosses(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'crosses'
                    WHEN ST_Touches(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'touches'
                    WHEN ST_Overlaps(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'overlaps'
                    WHEN ST_Intersects(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'intersects'
                    WHEN ST_Equals(ST_MakeValid(p1.geom::geometry), ST_MakeValid(p2.geom::geometry)) THEN 'equals'
                    ELSE 'disjoint'
                END AS relation,
                ST_Distance(p1.geom::geometry, p2.geom::geometry) AS distance  -- 使用 geography 类型计算距离
            FROM %s p1, %s p2
            WHERE p1.gid = %s AND p2.gid = %s;
        ''', (AsIs(self.pgchannel.geom_table_name), AsIs(self.pgchannel.geom_table_name), polygon1.gid, polygon2.gid))

        result = cur.fetchone()
        if result==None:
            return None,None
        topology, distance = result
        if topology=='equals':
            return None, None
        # 距离超过阈值则不建立关系
        if distance > self.MAX_RELATION_DISTANCE:
            return None,None
        # 从WKT创建几何对象
        geom1 = ogr.CreateGeometryFromWkt(polygon1.geo_wkt)
        geom2 = ogr.CreateGeometryFromWkt(polygon2.geo_wkt)
        if not geom1 or not geom2:
            raise ValueError("无法从WKT创建几何对象")
        # 确保几何对象有效
        if not geom1.IsValid():
            geom1 = geom1.MakeValid()
        if not geom2.IsValid():
            geom2 = geom2.MakeValid()

        # 计算标准化距离
        normalized_distance = self._calculate_normalized_distance(geom1, geom2)

        # 计算重叠面积(转换为平方米)
        if topology in ['contains', 'within', 'intersects', 'overlaps','crosses','covers']:
            overlapping_area = self._calculate_area_interaction(geom1, geom2)
        else:
            overlapping_area = 0.0  # 无面状重叠的情况
        #方位
        direction=None
        if topology == 'disjoint' or 'touches':
            direction = self._calculate_direction(geom1,geom2)

        # 功能语义
        sem = None
        if (polygon1.geo_type=='LINESTRING' and polygon2.geo_type in ['POLYGON','MULTIPOLYGON']):
            if polygon2.entity_type=='riverbank' and topology  == 'crosses':
                sem="桥梁或隧道"
            if polygon1.entity_type in ['residential','service']  and topology != 'disjoint':
                sem="交通服务"
        elif(polygon2.geo_type == 'LINESTRING' and polygon1.geo_type in ['POLYGON' , 'MULTIPOLYGON']):
            if polygon1.entity_type=='riverbank' and topology == 'crosses':
                sem="桥梁或隧道"
            if polygon1.entity_type in ['residential','service'] and topology != 'disjoint':
                sem="交通服务"
        elif (polygon1.geo_type in ['POLYGON', 'MULTIPOLYGON'] and polygon2.geo_type in ['POLYGON' , 'MULTIPOLYGON']):
            if topology in ['contains', 'within', 'intersects', 'touches', 'crosses']:
                sem = FUNCTIONAL_RELATIONS.get(
                    (polygon1.entity_type, polygon2.entity_type), None)

        # 创建 RelObject 实例
        rel_obj = RelObject(len(self.relations), polygon1, polygon2, topology, normalized_distance,distance, overlapping_area, sem, direction)
        #计算权重
        weight=self.spatial_weight_matrix.calculate_weight(rel_obj)
        rel_obj.spatialweight=weight

        # # 对应的反向关系
        # op_topology = topology
        # if topology=='contains':
        #     op_topology='within'
        # op_direction=self._calculate_direction(geom2,geom1)
        # op_sem=sem
        # op_rel_obj = RelObject(len(self.relations)+1, polygon2, polygon1, op_topology, normalized_distance, distance,
        #                     overlapping_area, op_sem, op_direction)

        return rel_obj,None

    def _convert_to_meters(self, distance, srid):
        """将距离转换为米"""
        cur = self.pgchannel.connection.cursor()
        cur.execute("""
            SELECT 
                CASE 
                    WHEN proj4text LIKE '%+units=m%' THEN 1.0
                    WHEN proj4text LIKE '%+units=ft%' THEN 0.3048
                    WHEN proj4text LIKE '%+units=us-ft%' THEN 0.304800609601
                    ELSE 1.0  # 默认假设单位为米
                END AS conversion_factor
            FROM spatial_ref_sys 
            WHERE srid = %s
        """, (srid,))
        result = cur.fetchone()
        return distance * (result[0] if result else 1.0)

    def _determine_topological_relation(self, geom1, geom2):
        """确定两个几何之间的拓扑关系"""
        if geom1.Contains(geom2):
            return 'contains'
        elif geom1.Within(geom2):
            return 'within'
        elif geom1.Overlaps(geom2):
            return 'overlaps'
        elif geom1.Touches(geom2):
            return 'touches'
        elif geom1.Crosses(geom2):
            return 'crosses'
        elif geom1.Intersects(geom2):
            return 'intersects'
        else:
            return 'disjoint'
    def _calculate_normalized_distance(self, geom1, geom2):
        """计算两个几何之间的距离(米) 并进行标准化处理
        """
        # 计算最小距离
        min_distance = geom1.Distance(geom2)

        # 计算两个几何的直径
        def calculate_diameter(geom):
            # 获取几何的外接矩形
            envelope = geom.GetEnvelope()  # 返回 (minX, maxX, minY, maxY)
            width = envelope[1] - envelope[0]
            height = envelope[3] - envelope[2]
            # 外接矩形的对角线长度作为直径的近似
            return math.sqrt(width ** 2 + height ** 2)

        diameter1 = calculate_diameter(geom1)
        diameter2 = calculate_diameter(geom2)
        max_diameter = max(diameter1, diameter2)

        # 避免除以零
        if max_diameter == 0:
            return 0.0

        # 计算标准化距离
        normalized_dist = min_distance / max_diameter

        return normalized_dist
    def _calculate_area_interaction(self, geom1, geom2):
        """安全计算面积交互（仅处理面状几何）"""
        if geom1.GetGeometryName() not in ['POLYGON', 'MULTIPOLYGON'] or \
                geom2.GetGeometryName() not in ['POLYGON', 'MULTIPOLYGON']:
            return 0.0

        intersection = geom1.Intersection(geom2)
        if not intersection or intersection.IsEmpty():
            return 0.0

        # 检查交集是否是面状
        if intersection.GetGeometryName() in ['POLYGON', 'MULTIPOLYGON']:
            min_area = min(geom1.GetArea(), geom2.GetArea())
            return intersection.GetArea() / min_area if min_area > 0 else 0.0
        return 0.0  # 线或点交集返回0
    def _calculate_direction(self, geom1, geom2):
        """计算相对方位（基于质心）"""

        def get_centroid_coords(geom):
            """安全获取质心坐标"""
            centroid = geom.Centroid()
            return (centroid.GetX(), centroid.GetY())  # 使用GetX()/GetY()方法

        x1, y1 = get_centroid_coords(geom1)
        x2, y2 = get_centroid_coords(geom2)

        dx = x2 - x1
        dy = y2 - y1

        # 计算方位角（弧度）
        angle = math.atan2(dy, dx)

        # 将弧度转换为方位描述
        directions = [
            (-math.pi / 8, math.pi / 8, "东"),
            (math.pi / 8, 3 * math.pi / 8, "东北"),
            (3 * math.pi / 8, 5 * math.pi / 8, "北"),
            (5 * math.pi / 8, 7 * math.pi / 8, "西北"),
            (7 * math.pi / 8, -7 * math.pi / 8, "西"),
            (-7 * math.pi / 8, -5 * math.pi / 8, "西南"),
            (-5 * math.pi / 8, -3 * math.pi / 8, "南"),
            (-3 * math.pi / 8, -math.pi / 8, "东南")
        ]

        for min_angle, max_angle, direction in directions:
            if min_angle <= angle < max_angle:
                return direction

        return "东"  # 默认方向

def process_shp_files(directory_path, outputfile, configuration_file, verbosity_on, reset_database):
    ''' Generate csv tables from SHP files in a given directory,
    use given configurations to interact with POSTGRESQL to execute POSTGIS actions. '''
    channel_inst = PostGISChannel(configuration_file, verbosity_on, reset_database)
    sgraph = GeoObjectsGraph(channel_inst)
    processed_files = 0
    """分块处理大型数据集"""
    start_time = time()
    geo_objects=[]
    try:
        for fname in listdir(directory_path):
            if fname.endswith(".shp"):
                it_start_time = time()
                fname_no_ext = fname.split('.shp')[0]
                shp_file = directory_path + '/' + fname
                fclrprint('Processing %s' % (shp_file), 'c')
                # 每个文件处理的对象 GeoObject
                one_geo_objects = GeoObject.from_shp(channel_inst,shp_file)
                if len(one_geo_objects)==0:
                    raise ValueError("0 GeoObject in file")
                geo_objects=geo_objects+one_geo_objects
                fclrprint('Map addition took %s' % (str(timedelta(seconds=int(time() - it_start_time))).zfill(8)), 'c')
    except Exception as e:
        fclrprint('Failed processing file %s\n%s' % (shp_file, str(e)), 'r')
        exit(-1)
    fclrprint('Generate GeoObject finished!', 'g')
    # 分批添加到图中
    batch_size = 500
    for i in range(0, len(geo_objects), batch_size):
        batch = geo_objects[i:i + batch_size]
        try:
            for geo_obj in batch:
                sgraph.add_geo_object_to_graph(geo_obj)
                sgraph.batch_store_relations()
                sgraph.relations.clear()
            fclrprint('Batch Add Relations!', 'g')

            # 定期清理内存
            if processed_files % 3 == 0:
                import gc
                gc.collect()
        except Exception as batch_e:
            fclrprint(f"Batch failed: {str(batch_e)}", 'y')
            # 跳过当前批次继续处理
            continue
        processed_files += 1

    fclrprint('Total running time %s' % (str(timedelta(seconds=int(time() - start_time))).zfill(8)), 'c')
    fclrprint('Total GeoObjects:'+str(len(sgraph.geo_objects))+'\nRelations:'+str(len(sgraph.relations)))

    sgraph.export_geom_jl_file(outputfile.replace('.jl', '.geom.jl'))
    sgraph.export_objects_jl_file(outputfile.replace('.jl', '.objects.jl'))
    sgraph.export_relations_jl_file(outputfile.replace('.jl', '.rel.jl'))

