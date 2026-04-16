# -*- coding: utf-8 -*-
import json
from argparse import ArgumentParser
from os.path import basename
from datetime import datetime
from json import loads
from baselutils import fclrprint
from rdflib import Graph, URIRef, Literal, XSD, Namespace
from rdflib.namespace import RDF, RDFS


GMG = Namespace('https://geomapgraph.org/resource/')  # 自定义命名空间 GMG
MY_ONT = Namespace('https://geomapgraph.org/ontology#') #自定义本体命名空间
GEO = Namespace('http://www.opengis.net/ont/geosparql#')#GeoSPARQL 的官方命名空间（Namespace），由开放地理空间联盟（OGC）制定，用于在语义网（Semantic Web）中表示和查询地理空间数据
DCTERMS = Namespace('http://purl.org/dc/terms/')#Dublin Core Metadata Terms（都柏林核心元数据术语集） 的官方命名空间（Namespace）

class LinkedMapGraph:
    ''' A graph holding the nodes and relations of the pre-processed maps. '''
    ''' 生成适合Cytoscape可视化的知识图谱 '''
    def __init__(self, json_file_name):
        ''' Init the linked map graph and read the WKT literals file,
        and map each gid to its WKT literal. '''

        self.dt = Graph()
        self.dt.bind('gmg', GMG)  # 修改为新的自定义命名空间 GMG
        self.dt.bind('geo', GEO)
        self.dt.bind('dcterms', DCTERMS)
        self.gid2wkt = dict()
        with open(json_file_name, "r") as read_file:
            for line_r in read_file:
                gid_wkt_entry = loads(line_r)
                self.gid2wkt[gid_wkt_entry['gid']] = gid_wkt_entry['wkt']

    def add_geo_node(self,geo_obj_gid, osm_id, geo_obj_name, geo_type, entity_type, area,length,file):
        ''' Add a geographic object to the graph '''

        geo_obj_uri = URIRef(GMG[str(osm_id)])  # 使用 GMG 命名空间
        self.dt.add((geo_obj_uri, RDF.type, GEO['Feature']))

        # geo:Geometry
        geo_geo_uri = URIRef(GMG[str(osm_id) + '_geom'])
        self.dt.add((geo_geo_uri, RDF.type, GEO['Geometry']))
        # geo:Feature --geo:hasGeometry--> geo:Geometry
        self.dt.add((geo_obj_uri, GEO['hasGeometry'], geo_geo_uri))
        # 将 WKT 数据绑定到 Geometry 节点
        self.dt.add((geo_geo_uri, GEO['asWKT'], Literal(self.gid2wkt[geo_obj_gid], datatype=GEO['wktLiteral'])))

        # 添加属性
        self.dt.add((geo_obj_uri, GMG['name'], Literal(geo_obj_name)))
        self.dt.add((geo_obj_uri, GMG['geoType'], Literal(geo_type)))
        self.dt.add((geo_obj_uri, GMG['entityType'], Literal(entity_type)))
        self.dt.add((geo_obj_uri, GMG['area'], Literal(area)))
        self.dt.add((geo_obj_uri, GMG['length'], Literal(length)))
        self.dt.add((geo_obj_uri, GMG['file'], Literal(file)))

    def add_geo_relation(self, polygon1_osm_id, polygon2_osm_id, topology,distance, normalized_distance,overlappingarea,direction,sem, spatialweight):
        ''' Link two geographic objects based on their relation. '''


        polygon1_uri = URIRef(GMG[str(polygon1_osm_id)])  # 使用 GMG 命名空间
        polygon2_uri = URIRef(GMG[str(polygon2_osm_id)])  # 使用 GMG 命名空间

        self.dt.add((MY_ONT['SpatialRelation'], RDF.type, RDFS.Class))
        # 创建关系URI
        relation_uri = URIRef(GMG[f"relation_{polygon1_osm_id}_{polygon2_osm_id}"])

        # 添加关系类型
        rel_type = {
            'intersects': GEO['sfIntersects'],
            'contains': GEO['sfContains'],
            'within': GEO['sfWithin'],
            'covers': GEO['sfCovers'],
            'overlaps': GEO['sfOverlaps'],
            'touches': GEO['sfTouches'],
            'disjoint': GEO['sfDisjoint'],
            'equals': GEO['sfEquals'],
            'crosses': GEO['sfCrosses']
        }.get(topology, GEO['sfDisjoint'])

        # 添加关系三元组
        self.dt.add((relation_uri, RDF.type, MY_ONT['SpatialRelation'])) # 类型是自定义

        # 创建连接关系 (实体1)-[关系]->(实体2)
        self.dt.add((polygon1_uri, GMG['hasSpatialRelation'], relation_uri))
        self.dt.add((relation_uri, GMG['relatesTo'], polygon2_uri))

        # 添加关系属性
        self.dt.add((relation_uri, GMG['topology'], Literal(topology)))
        if sem is not None:
            self.dt.add((relation_uri, GMG['sem'], Literal(sem)))
        if direction is not None:
            self.dt.add((relation_uri, GMG['direction'], Literal(direction)))
        if normalized_distance is not None:
            self.dt.add((relation_uri, GMG['normalized_distance'], Literal(normalized_distance, datatype=XSD.float)))
        if distance is not None:
            self.dt.add((relation_uri, GMG['distance'], Literal(distance, datatype=XSD.float)))
        if overlappingarea is not None:
            self.dt.add((relation_uri, GMG['overlappingArea'], Literal(overlappingarea, datatype=XSD.float)))
        if spatialweight is not None:
            self.dt.add((relation_uri, GMG['spatialWeight'], Literal(spatialweight, datatype=XSD.float)))

    def to_cytoscape_json(self):
        """生成完全兼容Cytoscape的JSON格式"""
        cy_elements = {
            'nodes': [],
            'edges': []
        }

        # 1. 添加地理实体节点
        for entity in self.dt.subjects(RDF.type, GEO['Feature']):
            node_data = {
                'id': str(entity),
                'ntype': "GeoEntity",
                'label': str(self.dt.value(entity, GMG['name'])) if str(self.dt.value(entity, GMG['name']))!="None" else str(self.dt.value(entity, GMG['entityType'])),
                'name': str(self.dt.value(entity, GMG['name'])) ,
                'entityType': str(self.dt.value(entity, GMG['entityType'])),
                'geoType': str(self.dt.value(entity, GMG['geoType'])),
                'gen_time': str(self.dt.value(entity, GMG['gen_time'])),
                'area': float(self.dt.value(entity, GMG['area'])) if self.dt.value(entity, GMG['area']) else 0.0
            }
            cy_elements['nodes'].append({
                'data': node_data
            })

        # 2. 添加空间关系节点
        for rel in self.dt.subjects(RDF.type, MY_ONT['SpatialRelation']):
            # 关系节点数据
            rel_data = {
                'id': str(rel),
                'ntype': "SpatialRelation",
                'label': str(self.dt.value(rel, GMG['topology'])),
                'topology': str(self.dt.value(rel, GMG['topology'])),
                'distance': float(self.dt.value(rel, GMG['distance'])) if self.dt.value(rel, GMG['distance']) else None,
                'overlappingArea': float(self.dt.value(rel, GMG['overlappingArea'])) if self.dt.value(rel, GMG['overlappingArea']) else None,
                'sem': str(self.dt.value(rel, GMG['sem'])),
                'weight': float(self.dt.value(rel, GMG['spatialWeight'])) if self.dt.value(rel, GMG[
                    'spatialWeight']) else 0.5
            }
            cy_elements['nodes'].append({
                'data': rel_data
            })

            # 3. 添加连接边 (实体->关系)
            for source in self.dt.subjects(GMG['hasSpatialRelation'], rel):
                cy_elements['edges'].append({
                    'data': {
                        'id': f"{str(source)}-{str(rel)}",
                        'source': str(source),
                        'target': str(rel),
                        'interaction': 'hasRelation'
                    }
                })

            # 4. 添加连接边 (关系->实体)
            for target in self.dt.objects(rel, GMG['relatesTo']):
                cy_elements['edges'].append({
                    'data': {
                        'id': f"{str(rel)}-{str(target)}",
                        'source': str(rel),
                        'target': str(target),
                        'interaction': 'relatesTo'
                    }
                })

        #return cy_elements
        return {'elements': cy_elements}

    def export_cytoscape_json(self, filename):
        ''' 导出Cytoscape JSON文件 '''
        cy_data = {
            'elements': self.to_cytoscape_json()['elements']
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(cy_data, f, indent=2, ensure_ascii=False)

def main():
    ap = ArgumentParser(
        description='Process geographic object output files (jl) and generate (ttl) file containing triples.\n\tUSAGE: python %s -g GEOMETRY_FILE -s OBJECTS_FILE -r RELATIONS_FILE' % (
            basename(__file__)))
    ap.add_argument('-g', '--geometry_file', help='File (jl) holding the geometry info (wkt).',default='geo_objects.geom.jl', type=str)
    ap.add_argument('-s', '--objects_file', help='File (jl) holding geographic objects info (metadata).',default='geo_objects.objects.jl', type=str)
    ap.add_argument('-r', '--relations_file', help='File (jl) holding relations info (spatial relations).',default='geo_objects.rel.jl', type=str)
    ap.add_argument('-o', '--output_file', help='The output file (ttl) with the generated triples.',
                    default='spatial.graph.ttl', type=str)

    args = ap.parse_args()

    # 在 main 函数中添加以下代码
    if args.geometry_file and args.relations_file and args.objects_file:
        fclrprint('Going to process files %s, %s, %s...' % (args.geometry_file, args.objects_file, args.relations_file))

        # 初始化 LinkedMapGraph 并生成 RDF 图
        lm_graph = LinkedMapGraph(args.geometry_file)
        # 加载地理对象信息
        with open(args.objects_file) as read_file:
            for line_r in read_file:
                geo_obj_dict = loads(line_r)
                lm_graph.add_geo_node(geo_obj_dict['gid'],geo_obj_dict['osm_id'], geo_obj_dict['name'], geo_obj_dict['geo_type'],
                                   geo_obj_dict['entity_type'],geo_obj_dict['area'],geo_obj_dict['length'],geo_obj_dict['file'])


        # 加载关系信息
        with open(args.relations_file) as read_file:
            for line_r in read_file:
                rel_dict = loads(line_r)
                lm_graph.add_geo_relation(rel_dict['polygon1_osm_id'], rel_dict['polygon2_osm_id'], rel_dict['topology'],
                                   rel_dict['distance'], rel_dict['normalized_distance'],rel_dict['overlapping_area'],
                                          rel_dict['direction'], rel_dict['sem'],rel_dict['spatialweight'])

        # 生成 RDF 文件
        lm_graph.dt.serialize(args.output_file, format="turtle")
        # 导出cytoscape可视化文件
        lm_graph.export_cytoscape_json('graph_visualization.json')

        fclrprint('Done, generated ttl file %s!' % (args.output_file), 'g')
    else:
        fclrprint('Geometry, objects and relations files were not provided.', 'r')
        exit(1)


if __name__ == '__main__':
    main()