# SpatialKG

A framework for automatic conversion of geospatial data (implemented using Shapefiles as an example) and converting it into multidimensional Spatial data as `RDF`. The resulting Geographic knowledge graphs can represent spatial relationships fusioning topology and metric to improve reasoning ability.

The process runs in three steps (see the following sections):
1. __Automatic extracting geometric features and calculating topological relationships__
2. __Adaptive Weight Calculation Based on Distance and Topological Relationships__
3. __Constructing Knowledge Graph  (`RDF`)__

This is the implementation accompanying the paper _MDSR-KG: A Geographical Knowledge Graph Framework For Representing and Quantifying Spatial Relationships_ published in ISPRS International Journal of Geo-Information.

------------------

### Preparing to run the program

The environment framework we use is [`anaconda`](https://www.anaconda.com/distribution/).

The dependencies should be installed. The `requirements.txt` file is:
```angular2html
GDAL==3.5.0
geopandas==0.10.2
opencv-python==4.6.0
openpyxl==3.1.3
Pillow==9.3.0
shapely==2.0.7
torch==1.13.1
torchaudio==0.13.1
torchvision==0.14.1
numpy==1.21.6
psycopg2==2.9.9
python==3.7.12
tqdm==4.62.3
```

------------------

## Automatic geometric feature processing

How to run:
```
python main.py -f <path_to_shapefiles>
               -r
               -o <path_to_output_file>
```
For example:
```
python main.py -f ./data/shapefiles -r -o geo_objects.jl
```
will produce the files: `geo_objects.geom.jl` (geometry), `geo_objects.objects.jl` (objects) and `geo_objects.rel.jl` (relations).
The relations include the Spatial Weight.


## Constructing Knowledge Graph

Constructing geographic knowledge graph following the GeosSPARQL standard. The `jl` files are toke as input to generate `RDF` data.

How to run:
```
python generate_graph.py -g <path_to_geometry_file>
                         -b <path_to_objects_file>
                         -r <path_to_relations_file>
                         -o <path_to_output_file>
```
For example:
```
python GenerateGraph.py -g geo_objects.geom.jl -b geo_objects.objects.jl -r geo_objects.rel.jl -o spatial.graph.ttl
```
will produce the file `spatial.graph.ttl`

------------------

### Citing

If you would like to cite this work in a paper or a presentation, the following is recommended (`BibTeX` entry):
如果您在研究中使用了本工具，请引用：

```bibtex
@article{shbita2023building,
  title={Building Spatio-Temporal Knowledge Graphs from Vectorized Topographic Historical Maps},
  author={Shbita, Basel and Knoblock, Craig A and Duan, Weiwei and Chiang, Yao-Yi and Uhl, Johannes H and Leyk, Stefan},
  journal={Semantic Web},
  year={2023},
  publisher={IOS Press}
}
```
