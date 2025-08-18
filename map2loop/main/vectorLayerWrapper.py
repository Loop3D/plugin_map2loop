import pandas as pd
import geopandas as gpd
from qgis.core import QgsRaster, QgsWkbTypes


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
