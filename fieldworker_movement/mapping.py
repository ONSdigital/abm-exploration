"""
Contains all functions relevant to building the NetworkX road network 
depiction for the field staff agent based model.

Aaron Stace, 03/07/2026
"""
import geopandas as gpd
import pandas as pd
import networkx as nx
from shapely import STRtree, Point
import neatnet

from pyproj import Transformer


# Reusable transformer: British National Grid → WGS84 (required by tile maps).
# future home: utils.py
TRANSFORMER_27700_TO_4326 = Transformer.from_crs("EPSG:27700", "EPSG:4326", 
                                                 always_xy=True)


def load_network_data(roads_file, paths_file):
    """
    Load the Newcastle road and path geopackage files, tag each with a 'type'
    edge attribute ('road' or 'path'), and return them as a single combined
    GeoDataFrame.
    """
    import time

    t0 = time.time()
    gdf_roads = gpd.read_file(roads_file)
    gdf_roads['type'] = 'road'
    print(f"  Roads loaded: {len(gdf_roads)} rows ({time.time() - t0:.1f}s)")

    t1 = time.time()
    gdf_paths = gpd.read_file(paths_file)
    gdf_paths['type'] = 'path'
    print(f"  Paths loaded: {len(gdf_paths)} rows ({time.time() - t1:.1f}s)")

    # Ensure both layers share the same CRS before any distance-based operations.
    if gdf_roads.crs != gdf_paths.crs:
        gdf_paths = gdf_paths.to_crs(gdf_roads.crs)

    gdf = pd.concat([gdf_roads, gdf_paths], ignore_index=True)
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    print(f"  Combined & exploded: {len(gdf)} rows")

    # Snap near-miss endpoints between the two layers (tolerance in CRS units;
    # EPSG:27700 is metres, so 1.0 = 1 metre).
    # NOTE: close_gaps is the slowest step — it inspects every endpoint against
    # every nearby geometry. For a city-scale network this can take 1-5 minutes.
    print("  Running neatnet.close_gaps (this is the slow step — please wait)...")
    t2 = time.time()
    gdf = neatnet.close_gaps(gdf, tolerance=1.0)
    print(f"  close_gaps done ({time.time() - t2:.1f}s)")

    return gdf


def build_graph_from_shapefile(gdf):
    """
    Builds a graph that matches the road layout on the shapefile. Made out of
    'nodes' and 'edges'. Edges are LineStrings, and nodes are their endpoints.

    Parameters:
    ----------
    gdf : GeoDataFrame
        A GeoDataFrame containing the road/path data with a geometry column.

    Returns:
    -------
    G : nx.Graph
        A NetworkX graph representing the road/path network.
    """
    G = nx.Graph()

    edge_list = []
    for row in gdf.itertuples(index=False):
        coords = list(row.geometry.coords)
        edge_len = row.geometry.length
        edge_type = row.type
        edge_list.extend(
            (start, end, {'length': edge_len, 'type': edge_type})
            for start, end in zip(coords[:-1], coords[1:])
        )

    G.add_edges_from(edge_list)
    nx.set_node_attributes(G, {node: node for node in G.nodes}, 'pos')

    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()

    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
    print(f"Connected components: {nx.number_connected_components(G)}")

    return G


def connect_components(G, tolerance=5.0):
    """
    Safety-net pass after graph construction. For any node that is not already
    in the largest connected component, find its nearest neighbour in that
    component (within `tolerance` CRS units) and insert a synthetic connector
    edge so agents can travel between the road and path networks.

    Connector edges carry type='connector' and length equal to the real
    Euclidean distance between the two nodes.

    Parameters
    ----------
    G : nx.Graph
        Graph returned by build_graph_from_shapefile.
    tolerance : float
        Maximum gap distance (metres if CRS is EPSG:27700) to bridge.

    Returns
    -------
    G : nx.Graph
        The same graph, mutated in-place, with connector edges added.
    """
    components = list(nx.connected_components(G))
    if len(components) == 1:
        print("connect_components: graph is already fully connected, nothing to do.")
        return G

    # Identify the largest component; everything else is a candidate.
    main_component = max(components, key=len)
    main_nodes = list(main_component)

    # Build a spatial index over the main-component nodes.
    main_points = [Point(n) for n in main_nodes]
    tree = STRtree(main_points)

    connectors_added = 0
    for component in components:
        if component is main_component:
            continue
        for node in component:
            pt = Point(node)
            # nearest_points returns (geometry_in_tree, query_point) in older
            # Shapely; STRtree.nearest returns the index of the nearest geometry.
            nearest_idx = tree.nearest(pt)
            nearest_node = main_nodes[nearest_idx]
            dist = pt.distance(Point(nearest_node))
            if dist <= tolerance:
                G.add_edge(node, nearest_node,
                           length=dist,
                           type='connector')
                connectors_added += 1

    print(f"connect_components: added {connectors_added} connector edge(s). "
          f"Components remaining: {nx.number_connected_components(G)}")
    return G


def load_addresses(address_csv_path):
    """
    Loads address frame in .csv form into the spatial model. The CSV must have,
    at minimum, columns: uprn, easting, northing.

    Parameters:
    ----------
    address_csv_path : str or Path
        Path to the .csv file that contains the address data.

    Returns:
    -------
    gdf : GeoDataFrame
        A GeoDataFrame containing the address data with a geometry column.
    """
    df = pd.read_csv(address_csv_path)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df['ai_easting'], df['ai_northing']),
        crs="EPSG:27700"
    )
    return gdf


def snap_addresses_to_nodes(gdf_addresses, G):
    """
    For each address in gdf_addresses, find the nearest node in the graph G
    and return a list of those nodes (as coordinate tuples), one per address.

    Parameters
    ----------
    gdf_addresses : GeoDataFrame
        Address points loaded by load_addresses().
    G : nx.Graph
        The road/path graph whose nodes are (x, y) coordinate tuples.

    Returns
    -------
    list of tuples
        One graph node per address, in the same order as gdf_addresses.
    """
    node_list = list(G.nodes())
    node_points = [Point(n) for n in node_list]
    tree = STRtree(node_points)

    return [node_list[tree.nearest(geom)] for geom in gdf_addresses.geometry]


def to_wgs84(eastings, northings):
    """
    Convert arrays of British National Grid (EPSG:27700) coordinates to
    WGS84 longitude/latitude (EPSG:4326) for use with tile-based maps.

    Parameters
    ----------
    eastings : array-like
    northings : array-like

    Returns
    -------
    lons, lats : tuple of lists
    """
    # future home: utils.py
    lons, lats = TRANSFORMER_27700_TO_4326.transform(list(eastings), list(northings))
    return lons, lats