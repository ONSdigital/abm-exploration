"""
Contains all functions relevant to building the NetworkX road network 
depiction for the field staff agent based model.

Aaron Stace, 03/07/2026
"""
import json
import geopandas as gpd
import pandas as pd
import networkx as nx
from shapely import STRtree, Point
import neatnet

from pyproj import Transformer
from config import NETWORK_CACHE_FILEPATH, ADDRESSES_DELIMITER, \
    COMPLETION_DELIMITER, EASTING_COLUMN, NORTHING_COLUMN, LSOA_CODE_COLUMN, \
    INITIAL_COMPLETION_COLUMN, ONGOING_COMPLETION_COLUMN, \
    DEFAULT_INITIAL_COMPLETION_RATE, DEFAULT_ONGOING_COMPLETION_RATE


# Reusable transformer: British National Grid → WGS84 (required by tile maps).
# future home: utils.py
TRANSFORMER_27700_TO_4326 = Transformer.from_crs("EPSG:27700", "EPSG:4326", 
                                                 always_xy=True)


def load_network_data(roads_file, paths_file, tolerance=1.0, cache_file=None):
    """
    Load the Newcastle road and path geopackage files, tag each with a 'type'
    edge attribute ('road' or 'path'), and return them as a single combined
    GeoDataFrame.

    The cache is written automatically after the first successful run. Delete 
    the cache file to force a rebuild (e.g. after updating the source shapefiles).
    """
    import os
    import time

    if cache_file is None:
        cache_file = NETWORK_CACHE_FILEPATH

    if os.path.exists(cache_file):
        print(f"  Loading network from cache: {cache_file}")
        t0 = time.time()
        gdf = gpd.read_file(cache_file)
        print(f"  Cache loaded ({time.time() - t0:.1f}s)")
        return gdf

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
    gdf = neatnet.close_gaps(gdf, tolerance=tolerance)
    print(f"  close_gaps done ({time.time() - t2:.1f}s)")

    print(f"  Saving network cache to: {cache_file}")
    gdf.to_file(cache_file, driver="GPKG")

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

    for row in gdf.itertuples(index=False):
        coords = list(row.geometry.coords)
        edge_len = row.geometry.length
        edge_type = row.type
        G.add_edges_from(
            (start, end, {'length': edge_len, 'type': edge_type})
            for start, end in zip(coords[:-1], coords[1:])
        )
    nx.set_node_attributes(G, {node: node for node in G.nodes}, 'pos')

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
    df = pd.read_csv(address_csv_path, sep=ADDRESSES_DELIMITER,
                     low_memory=False)
    # If pandas starts having dtype problems, add dtype={LSOA_CODE_COLUMN: str}
    # (for example) for the columns as kwargs.

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[EASTING_COLUMN], df[NORTHING_COLUMN]),
        crs="EPSG:27700"
    )
    return gdf


def load_lsoa_completion_rates(completion_csv_path):
    """
    Load flat per-LSOA electronic survey completion rates from CSV.

    The CSV must contain the LSOA code plus separate columns for the initial
    pre-fieldwork completion share and the ongoing per-step completion chance.
    """
    df = pd.read_csv(completion_csv_path, sep=COMPLETION_DELIMITER,
                     low_memory=False)

    required_columns = {
        LSOA_CODE_COLUMN,
        INITIAL_COMPLETION_COLUMN,
        ONGOING_COMPLETION_COLUMN,
    }
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        missing = ', '.join(sorted(missing_columns))
        raise ValueError(
            f"Missing required completion-rate column(s): {missing}"
        )

    duplicate_mask = df[LSOA_CODE_COLUMN].astype(str).duplicated(keep=False)
    if duplicate_mask.any():
        duplicates = sorted(df.loc[duplicate_mask, LSOA_CODE_COLUMN].astype(str).unique())
        raise ValueError(
            "Duplicate LSOA completion-rate rows found for: "
            + ', '.join(duplicates)
        )

    rates = {}
    for row in df.itertuples(index=False):
        lsoa_code = str(getattr(row, LSOA_CODE_COLUMN)).strip()
        initial_rate = getattr(row, INITIAL_COMPLETION_COLUMN)
        ongoing_rate = getattr(row, ONGOING_COMPLETION_COLUMN)

        initial_rate = DEFAULT_INITIAL_COMPLETION_RATE if \
                                pd.isna(initial_rate) else float(initial_rate)
        ongoing_rate = DEFAULT_ONGOING_COMPLETION_RATE if \
                                pd.isna(ongoing_rate) else float(ongoing_rate)

        for rate_name, rate_value in (
            (INITIAL_COMPLETION_COLUMN, initial_rate),
            (ONGOING_COMPLETION_COLUMN, ongoing_rate),
        ):
            if not 0.0 <= rate_value <= 1.0:
                raise ValueError(
                    f"{rate_name} for {lsoa_code} must be between 0 and 1."
                )

        rates[lsoa_code] = {
            INITIAL_COMPLETION_COLUMN: initial_rate,
            ONGOING_COMPLETION_COLUMN: ongoing_rate,
        }

    return rates


def snap_addresses_to_nodes(gdf_addresses, G):
    """
    For each address in gdf_addresses, find the nearest node in the graph G
    and return a list of (node, lsoa_code) pairs, one per address.

    Parameters
    ----------
    gdf_addresses : GeoDataFrame
        Address points loaded by load_addresses(). Must contain a
        'gi_lsoa_code' column.
    G : nx.Graph
        The road/path graph whose nodes are (x, y) coordinate tuples.

    Returns
    -------
    list of (tuple, str)
        Each element is (graph_node, lsoa_code) in the same order as
        gdf_addresses.
    """
    node_list = list(G.nodes())
    node_points = [Point(n) for n in node_list]
    tree = STRtree(node_points)

    return [
        (node_list[tree.nearest(geom)], lsoa)
        for geom, lsoa in zip(gdf_addresses.geometry,
                               gdf_addresses[LSOA_CODE_COLUMN])
    ]


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


def load_lsoa_geojson(lsoa_filepath, lsoa_code_column):
    """
    Load an LSOA polygon shapefile/geopackage, reproject to WGS84, and return
    a GeoJSON FeatureCollection dict, ordered LSOA codes, and ordered names.

    The GeoJSON features have their 'id' field set to the LSOA code so that
    Plotly's Choroplethmapbox can match them against the 'locations' array.

    Parameters
    ----------
    lsoa_filepath : str
        Path to the LSOA polygon file (.gpkg, .shp, etc.).
    lsoa_code_column : str
        Name of the column in the file that holds the LSOA code
        ('LSOA21CD').

    Returns
    -------
    geojson : dict
        GeoJSON FeatureCollection compatible with go.Choroplethmapbox.
    lsoa_ids : list of str
        LSOA codes in the same order as the features.
    lsoa_names : list of str
        LSOA labels for hover display (from the LSOA code column).
    """
    gdf = gpd.read_file(lsoa_filepath)
    gdf = gdf.to_crs("EPSG:4326")

    gdf = gdf[[lsoa_code_column, 'geometry']].copy()
    gdf['lsoa_name'] = gdf[lsoa_code_column].astype(str)

    gdf = gdf.rename(columns={lsoa_code_column: 'lsoa_code'})

    geojson = json.loads(gdf.to_json())

    # Choroplethmapbox requires feature['id'] at the top level (not just inside
    # properties) to match against the 'locations' array.
    for feature in geojson['features']:
        feature['id'] = feature['properties']['lsoa_code']

    lsoa_ids = [f['id'] for f in geojson['features']]
    lsoa_names = [f['properties']['lsoa_name'] for f in geojson['features']]
    return geojson, lsoa_ids, lsoa_names