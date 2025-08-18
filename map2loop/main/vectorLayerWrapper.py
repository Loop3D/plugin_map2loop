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

def GeoDataFrameToQgsLayer(qgs_algorithm, geodataframe, parameters, context, output_key, feedback=None):
    """
    Write a GeoPandas GeoDataFrame directly to a QGIS Processing FeatureSink.

    Parameters
    ----------
    alg : QgsProcessingAlgorithm (self)
    gdf : geopandas.GeoDataFrame
    parameters : dict (from processAlgorithm)
    context : QgsProcessingContext
    output_key : str  (e.g. self.OUTPUT)
    feedback : QgsProcessingFeedback | None

    Returns
    -------
    str : dest_id to return from processAlgorithm, e.g. { output_key: dest_id }
    """
    import pandas as pd
    import numpy as np
    from shapely.geometry import (
        Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
    )

    from qgis.core import (
        QgsFields, QgsField, QgsFeature, QgsGeometry,
        QgsWkbTypes, QgsCoordinateReferenceSystem, QgsFeatureSink
    )
    from qgis.PyQt.QtCore import QVariant, QDateTime

    if feedback is None:
        class _Dummy:
            def pushInfo(self, *a, **k): pass
            def reportError(self, *a, **k): pass
            def setProgress(self, *a, **k): pass
            def isCanceled(self): return False
        feedback = _Dummy()

    if geodataframe is None:
        raise ValueError("GeoDataFrame is None")
    if geodataframe.empty:
        feedback.pushInfo("Input GeoDataFrame is empty; creating empty output layer.")

    # --- infer WKB type (family, Multi, Z)
    def _infer_wkb(series):
        base = None
        any_multi = False
        has_z = False
        for geom in series:
            if geom is None: continue
            if getattr(geom, "is_empty", False): continue
            # multi?
            if isinstance(geom, (MultiPoint, MultiLineString, MultiPolygon)):
                any_multi = True
                g0 = next(iter(getattr(geom, "geoms", [])), None)
                gt = getattr(g0, "geom_type", None) or None
            else:
                gt = getattr(geom, "geom_type", None)

            # base family
            if gt in ("Point", "LineString", "Polygon"):
                base = gt
                # z?
                try:
                    has_z = has_z or bool(getattr(geom, "has_z", False))
                except Exception:
                    pass
                if base:
                    break

        if base is None:
            # default safely to LineString if everything is empty; adjust if you prefer Point/Polygon
            base = "LineString"

        fam = {
            "Point": QgsWkbTypes.Point,
            "LineString": QgsWkbTypes.LineString,
            "Polygon": QgsWkbTypes.Polygon,
        }[base]

        if any_multi:
            fam = QgsWkbTypes.multiType(fam)
        if has_z:
            fam = QgsWkbTypes.addZ(fam)
        return fam

    wkb_type = _infer_wkb(geodataframe.geometry)

    # --- build CRS from gdf.crs
    crs = QgsCoordinateReferenceSystem()
    if geodataframe.crs is not None:
        try:
            crs = QgsCoordinateReferenceSystem.fromWkt(geodataframe.crs.to_wkt())
        except Exception:
            try:
                epsg = geodataframe.crs.to_epsg()
                if epsg:
                    crs = QgsCoordinateReferenceSystem.fromEpsgId(int(epsg))
            except Exception:
                pass

    # --- build QGIS fields from pandas dtypes
    fields = QgsFields()
    non_geom_cols = [c for c in geodataframe.columns if c != geodataframe.geometry.name]

    def _qvariant_type(dtype) -> QVariant.Type:
        if pd.api.types.is_integer_dtype(dtype):
            return QVariant.Int
        if pd.api.types.is_float_dtype(dtype):
            return QVariant.Double
        if pd.api.types.is_bool_dtype(dtype):
            return QVariant.Bool
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return QVariant.DateTime
        return QVariant.String

    for col in non_geom_cols:
        fields.append(QgsField(str(col), _qvariant_type(geodataframe[col].dtype)))

    # --- create sink
    sink, dest_id = qgs_algorithm.parameterAsSink(
        parameters,
        output_key,
        context,
        fields,
        wkb_type,
        crs,
    )
    if sink is None:
        from qgis.core import QgsProcessingException
        raise QgsProcessingException("Could not create output sink")

    # --- write features
    total = len(geodataframe.index)
    is_multi_sink = QgsWkbTypes.isMultiType(wkb_type)

    for i, (_, row) in enumerate(geodataframe.iterrows()):
        if feedback.isCanceled():
            break

        geom = row[geodataframe.geometry.name]
        if geom is None or getattr(geom, "is_empty", False):
            continue

        # promote single → multi if needed
        if is_multi_sink:
            if isinstance(geom, Point):
                geom = MultiPoint([geom])
            elif isinstance(geom, LineString):
                geom = MultiLineString([geom])
            elif isinstance(geom, Polygon):
                geom = MultiPolygon([geom])

        f = QgsFeature(fields)

        # attributes in declared order
        attrs = []
        for col in non_geom_cols:
            val = row[col]
            if isinstance(val, np.generic):
                try:
                    val = val.item()
                except Exception:
                    pass
            if pd.api.types.is_datetime64_any_dtype(geodataframe[col].dtype):
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

        sink.addFeature(f, QgsFeatureSink.FastInsert)

        if total:
            feedback.setProgress(int(100.0 * (i + 1) / total))

    return dest_id

