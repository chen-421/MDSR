from argparse import ArgumentParser
from os.path import basename
from baselutils import fclrprint
from GeoObjectSHP import  process_shp_files

def main():
    ap = ArgumentParser(
        description='Process SHP files and generate (jl) files with geographic object info.\n\tUSAGE: python %s -d DIR_NAME -c CONFIG_FILE' % (
            basename(__file__)))
    ap.add_argument('-d', '--dir_name', help='Directory path with SHP files.',default='./data/test', type=str)
    ap.add_argument('-o', '--output_file', help='Output geometry file (jl).', default='geo_objects.jl', type=str)
    ap.add_argument('-c', '--config_file', help='Input configuration file.', default='config.json', type=str)
    ap.add_argument('-v', '--debug_prints', help='Print additional debug prints.', default=False, action='store_true')
    ap.add_argument('-r', '--reset_db', help='Reset Databases prior to processing.', default=False, action='store_true')

    args = ap.parse_args()

    if args.dir_name:
        fclrprint('Going to process SHP files in dir %s using configurations from file %s...' \
                  % (args.dir_name, args.config_file))
        process_shp_files(args.dir_name,  args.output_file,args.config_file, args.debug_prints, args.reset_db)
    else:
        fclrprint('Input directory and configuration file were not provided.', 'r')
        exit(1)


# 在 main.py 中添加土地覆盖实验选项
def main2():
    ap = ArgumentParser(
        description='MDSR-KG 地理知识图谱构建与实验系统')
    ap.add_argument('-d', '--dir_name', help='SHP文件目录', default='./data', type=str)
    ap.add_argument('-o', '--output_file', help='输出文件', default='geo_objects.jl', type=str)
    ap.add_argument('-c', '--config_file', help='配置文件', default='config.json', type=str)
    ap.add_argument('-v', '--debug_prints', help='打印调试信息', default=False, action='store_true')
    ap.add_argument('-r', '--reset_db', help='重置数据库', default=False, action='store_true')
    # 新增土地覆盖实验参数
    ap.add_argument('-lc', '--land_cover_experiment', help='运行土地覆盖分析实验', default=False, action='store_true')
    ap.add_argument('-export', '--export_data', help='导出实验数据文件', default='land_cover_results.json', type=str)

    args = ap.parse_args()

    if args.land_cover_experiment:
        # 运行土地覆盖实验
        fclrprint('运行土地覆盖分析实验...', 'g')
        try:
            from land_cover_experiment import run_land_cover_experiment

            # 这里需要先构建图，然后运行实验
            # 实际使用时需要根据您的数据加载逻辑调整
            fclrprint('请确保已先构建知识图谱，然后运行土地覆盖实验', 'y')
            # 示例：run_land_cover_experiment(sgraph.geo_objects, sgraph.relations, args.export_data)

        except ImportError as e:
            fclrprint(f'土地覆盖实验模块导入失败: {e}', 'r')

    elif args.dir_name:
        # 正常处理SHP文件
        process_shp_files(args.dir_name, args.output_file, args.config_file, args.debug_prints, args.reset_db)
    else:
        fclrprint('请提供输入目录或使用实验选项', 'r')

if __name__ == '__main__':
    main()