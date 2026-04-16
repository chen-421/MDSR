# MDSR_KGToNeo4j_optimized.py
from neo4j import GraphDatabase
import json
import time

uri = "bolt://localhost:7687"
username = "neo4j"
password = "123456"

driver = GraphDatabase.driver(uri, auth=(username, password))


def delete_indexes_correct():
    """正确删除索引"""
    with driver.session() as session:
        print("🔧 开始删除索引...")

        # 从你的输出中可以看到具体的索引描述
        indexes_to_delete = [
            "INDEX ON :GeoEntity(gid)",
            "INDEX ON :GeoEntity(name)",
            "INDEX ON :GeoEntity(entity_type)",
            "INDEX ON :SpatialRelation(relation_id)",
            "INDEX ON :SpatialRelation(topology)"
        ]

        for index_desc in indexes_to_delete:
            try:
                # 正确的删除语法
                session.run(f"DROP {index_desc}")
                print(f"✅ 删除索引: {index_desc}")
            except Exception as e:
                print(f"⚠️ 删除失败 {index_desc}: {e}")

        print("\n✅ 索引删除完成！")


def check_indexes():
    """检查索引状态"""
    with driver.session() as session:
        print("\n📊 检查当前索引状态...")
        try:
            result = session.run("CALL db.indexes()")
            remaining_indexes = list(result)
            if remaining_indexes:
                print("仍存在的索引:")
                for record in remaining_indexes:
                    print(f"  - {record['description']}")
            else:
                print("✅ 所有索引已删除！")
        except Exception as e:
            print(f"检查索引状态失败: {e}")

def create_indexes():
    """创建MDSR-KG专用索引"""
    with driver.session() as session:
        indexes = [
            "CREATE INDEX ON :GeoEntity(gid)",
            "CREATE INDEX ON :SpatialRelation(relation_id)",
            "CREATE INDEX ON :GeoEntity(name)",
            "CREATE INDEX ON :GeoEntity(entity_type)",
            "CREATE INDEX ON :SpatialRelation(topology)"
        ]

        for index_query in indexes:
            try:
                session.run(index_query)
                print(f"✅ 创建索引: {index_query}")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"ℹ️  索引已存在: {index_query}")
                else:
                    print(f"⚠️  创建索引异常: {index_query} - {e}")


def _clean_relation_data(rel):
    """清理关系数据，处理null值"""
    cleaned_rel = rel.copy()

    # 为可能为null的属性设置默认值
    if cleaned_rel.get('direction') is None:
        cleaned_rel['direction'] = 'none'
    if cleaned_rel.get('sem') is None:
        cleaned_rel['sem'] = 'none'
    if cleaned_rel.get('spatialweight') is None:
        cleaned_rel['spatialweight'] = 0.0
    if cleaned_rel.get('distance') is None:
        cleaned_rel['distance'] = 0.0
    if cleaned_rel.get('overlapping_area') is None:
        cleaned_rel['overlapping_area'] = 0.0

    return cleaned_rel


def import_mdsr_kg_knowledge_graph():
    """导入知识图谱：MDSR-KG结构 - 优化版"""

    # 0. 创建索引
    print("步骤0: 创建索引...")
    create_indexes()

    # 1. 导入所有地理实体节点
    print("步骤1: 导入地理实体节点...")
    entity_count = 0
    start_time = time.time()

    with open("geo_objects.objects.jl", "r", encoding="utf-8") as f:
        batch = []
        for line_num, line in enumerate(f, 1):
            if line.strip():
                obj = json.loads(line)
                batch.append(obj)

                # 增大批次大小到5000
                if len(batch) >= 5000:
                    _import_entities_batch(batch)
                    entity_count += len(batch)
                    batch = []

                    # 显示进度
                    elapsed = time.time() - start_time
                    speed = entity_count / elapsed if elapsed > 0 else 0
                    print(f"✅ 已导入 {entity_count} 个实体节点 - 速度: {speed:.1f} 节点/秒")

        if batch:
            _import_entities_batch(batch)
            entity_count += len(batch)

    total_time = time.time() - start_time
    print(
        f"🎉 地理实体导入完成，共 {entity_count} 个节点 - 耗时: {total_time:.2f}秒 - 平均速度: {entity_count / total_time:.1f} 节点/秒")

    # 2. 导入空间关系节点和连接边
    print("步骤2: 导入空间关系和连接边...")
    relation_count = 0
    start_time = time.time()

    with open("geo_objects.rel.jl", "r", encoding="utf-8") as f:
        batch = []
        for line_num, line in enumerate(f, 1):
            if line.strip():
                rel = json.loads(line)
                # 清理数据，处理null值
                cleaned_rel = _clean_relation_data(rel)
                batch.append(cleaned_rel)

                # 增大批次大小到2000
                if len(batch) >= 2000:
                    success_count = _import_relations_batch(batch)
                    relation_count += success_count
                    batch = []

                    # 显示进度
                    elapsed = time.time() - start_time
                    speed = relation_count / elapsed if elapsed > 0 else 0
                    if relation_count % 50000 == 0:
                        print(f"✅ 已导入 {relation_count} 个空间关系 - 速度: {speed:.1f} 关系/秒")

        if batch:
            success_count = _import_relations_batch(batch)
            relation_count += success_count

    total_time = time.time() - start_time
    print(
        f"🎉 空间关系导入完成，共 {relation_count} 个关系节点 - 耗时: {total_time:.2f}秒 - 平均速度: {relation_count / total_time:.1f} 关系/秒")


def _import_entities_batch(batch):
    """批量导入地理实体节点 - 优化版"""
    with driver.session() as session:
        query = """
        UNWIND $batch AS entity
        MERGE (e:GeoEntity {gid: entity.gid})
        SET e.name = entity.name,
            e.entity_type = entity.entity_type,
            e.geo_type = entity.geo_type,
            e.area = toFloat(entity.area),
            e.length = toFloat(entity.length),
            e.osm_id = entity.osm_id
        """
        session.run(query, batch=batch)


def _import_relations_batch(batch):
    """批量导入空间关系节点和连接边 - 优化版"""
    try:
        with driver.session() as session:
            query = """
            UNWIND $batch AS rel
            // 找到两个地理实体
            MATCH (a:GeoEntity {gid: rel.from_gid})
            MATCH (b:GeoEntity {gid: rel.to_gid})
            // 创建空间关系节点（确保所有属性都有值）
            CREATE (r:SpatialRelation {
                relation_id: rel.from_gid + '_' + rel.to_gid,
                topology: rel.topology,
                distance: toFloat(rel.distance),
                semantic: rel.sem,
                spatial_weight: toFloat(rel.spatialweight),
                direction: rel.direction,
                overlapping_area: toFloat(rel.overlapping_area)
            })
            // 创建连接边：实体A -> 关系节点 -> 实体B
            CREATE (a)-[:hasSpatialRelation]->(r)
            CREATE (r)-[:relatesTo]->(b)
            RETURN count(r) as created_count
            """
            result = session.run(query, batch=batch)
            return result.single()['created_count']
    except Exception as e:
        print(f"❌ 批量导入关系失败: {e}")
        # 如果批量失败，尝试单条导入
        success_count = 0
        for rel in batch:
            try:
                with driver.session() as session:
                    session.run(query, batch=[rel])
                    success_count += 1
            except Exception as single_error:
                print(f"❌ 单条关系导入失败: {rel.get('from_gid')} -> {rel.get('to_gid')}, 错误: {single_error}")
        return success_count


def test_query():
    """测试查询：验证图谱结构"""
    with driver.session() as session:
        result = session.run("""
        MATCH (a:GeoEntity)-[:hasSpatialRelation]->(r:SpatialRelation)-[:relatesTo]->(b:GeoEntity)
        RETURN a.osm_id as entityA, r.topology as relation, b.osm_id as entityB
        LIMIT 10
        """)

        print("\n图谱结构验证（前10个关系）：")
        for record in result:
            print(f"{record['entityA']} --[{record['relation']}]--> {record['entityB']}")

        # 检查数据完整性
        result = session.run("""
        MATCH (e:GeoEntity) RETURN count(e) as entity_count
        """)
        entity_count = result.single()['entity_count']

        result = session.run("""
        MATCH (sr:SpatialRelation) RETURN count(sr) as relation_count
        """)
        relation_count = result.single()['relation_count']

        print(f"\n数据完整性检查:")
        print(f"实体节点数: {entity_count}")
        print(f"关系节点数: {relation_count}")


def clear_database():
    """清空整个数据库"""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("✅ 数据库已清空")

def create_one_critical_index():
    """只创建一个最重要的索引"""
    with driver.session() as session:
        # 只加这个复合索引，对Q4-Q6都有帮助
        session.run("CREATE INDEX ON :GeoEntity(entity_type, gid)")
        print("✅ 创建关键复合索引")
if __name__ == "__main__":
    try:
        check_indexes()
        clear_database()
        import time

        start_time = time.time()
        import_mdsr_kg_knowledge_graph()
        end_time = time.time()
        print(f"构建耗时: {end_time - start_time:.2f} 秒")

        test_query()
        print("✅ MDSR-KG知识图谱导入成功！")
    except Exception as e:
        print(f"❌ 导入失败: {e}")
    finally:
        driver.close()