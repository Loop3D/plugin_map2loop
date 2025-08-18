from qgis.core import (
        QgsVectorLayer, 
        QgsFields, 
        QgsField,
        QgsFeature,
        QgsGeometry,
        QgsWkbTypes, 
        QgsCoordinateReferenceSystem, 
        QgsProject, 
        QgsRaster
    )
from qgis.PyQt.QtCore import QVariant, QDateTime

from shapely.geometry import Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
import pandas as pd
import geopandas as gpd
   


def qgsLayerToGeoDataFrame(layer) -> gpd.GeoDataFrame:
    if layer is None:
        return None
    features = layer.getFeatures()
    fields = layer.fields()
    data = {'geometry': []}
    for f in fields:
        data[f.name()] = []
    for feature in features:
        geom = feature.geometry()
        if geom.isEmpty():
            continue
        data['geometry'].append(geom)
        for f in fields:
            data[f.name()].append(feature[f.name()])
    return gpd.GeoDataFrame(data, crs=layer.crs().authid())


def qgsLayerToDataFrame(layer, dtm) -> pd.DataFrame:
    """Convert a vector layer to a pandas DataFrame
    samples the geometry using either points or the vertices of the lines

    :param layer: _description_
    :type layer: _type_
    :param dtm: Digital Terrain Model to evaluate Z values
    :type dtm: _type_ or None
    :return: the dataframe object
    :rtype: pd.DataFrame
    """
    if layer is None:
        return None
    fields = layer.fields()
    data = {}
    data['X'] = []
    data['Y'] = []
    data['Z'] = []

    for field in fields:
        data[field.name()] = []
    for feature in layer.getFeatures():
        geom = feature.geometry()
        points = []
        if geom.isMultipart():
            if geom.type() == QgsWkbTypes.PointGeometry:
                points = geom.asMultiPoint()
            elif geom.type() == QgsWkbTypes.LineGeometry:
                for line in geom.asMultiPolyline():
                    points.extend(line)
                # points = geom.asMultiPolyline()[0]
        else:
            if geom.type() == QgsWkbTypes.PointGeometry:
                points = [geom.asPoint()]
            elif geom.type() == QgsWkbTypes.LineGeometry:
                points = geom.asPolyline()

        for p in points:
            data['X'].append(p.x())
            data['Y'].append(p.y())
            if dtm is not None:
                # Replace with your coordinates

                # Extract the value at the point
                z_value = dtm.dataProvider().identify(p, QgsRaster.IdentifyFormatValue)
                if z_value.isValid():
                    z_value = z_value.results()[1]
                else:
                    z_value = -9999
                data['Z'].append(z_value)
            if dtm is None:
                data['Z'].append(0)
            for field in fields:
                data[field.name()].append(feature[field.name()])
    return pd.DataFrame(data)

def gdf_to_qgis_layer(gdf, layer_name="from_gdf"):
    """
    Convert a GeoPandas GeoDataFrame to a QGIS memory layer (QgsVectorLayer).
    Keeps attributes and CRS. Works for Point/LineString/Polygon and their Multi*.
    """

    if gdf is None or gdf.empty:
        raise ValueError("GeoDataFrame is empty")

    # --- infer geometry type from first non-empty geometry
    def infer_wkb(geoms):
        for g in geoms:
            if g is None:
                continue
            if hasattr(g, "is_empty") and g.is_empty:
                continue
            if isinstance(g, MultiPoint):       return QgsWkbTypes.MultiPoint
            if isinstance(g, Point):            return QgsWkbTypes.Point
            if isinstance(g, MultiLineString):  return QgsWkbTypes.MultiLineString
            if isinstance(g, LineString):       return QgsWkbTypes.LineString
            if isinstance(g, MultiPolygon):     return QgsWkbTypes.MultiPolygon
            if isinstance(g, Polygon):          return QgsWkbTypes.Polygon
        raise ValueError("Could not infer geometry type (all geometries empty?)")

    wkb_type = infer_wkb(gdf.geometry)

    # --- build CRS
    crs_qgis = QgsCoordinateReferenceSystem()
    if gdf.crs is not None:
        try:
            crs_qgis = QgsCoordinateReferenceSystem.fromWkt(gdf.crs.to_wkt())
        except Exception:
            epsg = gdf.crs.to_epsg()
            if epsg:
                crs_qgis = QgsCoordinateReferenceSystem.fromEpsgId(int(epsg))

    geom_str = QgsWkbTypes.displayString(wkb_type)  # e.g. "LineString"
    uri = f"{geom_str}?crs={crs_qgis.authid()}" if crs_qgis.isValid() else geom_str
    layer = QgsVectorLayer(uri, layer_name, "memory")
    prov = layer.dataProvider()

    # --- fields: map pandas dtypes → QGIS
    import numpy as np
    fields = QgsFields()
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        dtype = gdf[col].dtype
        if pd.api.types.is_integer_dtype(dtype):
            qtype = QVariant.Int
        elif pd.api.types.is_float_dtype(dtype):
            qtype = QVariant.Double
        elif pd.api.types.is_bool_dtype(dtype):
            qtype = QVariant.Bool
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            qtype = QVariant.DateTime
        else:
            qtype = QVariant.String
        fields.append(QgsField(str(col), qtype))
    prov.addAttributes(list(fields))
    layer.updateFields()

    # --- features
    feats = []
    non_geom_cols = [c for c in gdf.columns if c != gdf.geometry.name]

    for _, row in gdf.iterrows():
        geom = row[gdf.geometry.name]
        if geom is None or (hasattr(geom, "is_empty") and geom.is_empty):
            continue

        f = QgsFeature(fields)

        # attributes in declared order with type cleanup
        attrs = []
        for col in non_geom_cols:
            val = row[col]
            # numpy scalar → python scalar
            if isinstance(val, (np.generic,)):
                try:
                    val = val.item()
                except Exception:
                    pass
            # pandas Timestamp → QDateTime (if column is datetime)
            if pd.api.types.is_datetime64_any_dtype(gdf[col].dtype):
                if pd.isna(val):
                    val = None
                else:
                    val = QDateTime(val.to_pydatetime())
            attrs.append(val)
        f.setAttributes(attrs)

        # geometry (shapely → QGIS)
        try:
            f.setGeometry(QgsGeometry.fromWkb(geom.wkb))
        except Exception:
            f.setGeometry(QgsGeometry.fromWkt(geom.wkt))

        feats.append(f)

    if feats:
        prov.addFeatures(feats)
        layer.updateExtents()

    return layer  # optionally: QgsProject.instance().addMapLayer(layer)
