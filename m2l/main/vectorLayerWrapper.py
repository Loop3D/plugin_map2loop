# PyQGIS / PyQt imports

from qgis.core import (
        QgsRaster,
        QgsFields, 
        QgsField, 
        QgsFeature, 
        QgsGeometry,
        QgsWkbTypes, 
        QgsCoordinateReferenceSystem, 
        QgsFeatureSink,
        QgsProcessingException,
        QgsPoint,
        QgsPointXY,
    )

from qgis.PyQt.QtCore import QVariant, QDateTime, QVariant

from shapely.geometry import Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
from shapely.wkb import loads as wkb_loads
import pandas as pd
import geopandas as gpd
import numpy as np
   


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


# ---------- helpers ----------

def _qvariant_type_from_dtype(dtype) -> QVariant.Type:
    """Map a pandas dtype to a QVariant type."""
    import numpy as np
    if np.issubdtype(dtype, np.integer):
        # prefer 64-bit when detected
        try:
            return QVariant.LongLong
        except AttributeError:
            return QVariant.Int
    if np.issubdtype(dtype, np.floating):
        return QVariant.Double
    if np.issubdtype(dtype, np.bool_):
        return QVariant.Bool
    # datetimes
    try:
        import pandas as pd
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return QVariant.DateTime
        if pd.api.types.is_datetime64_ns_dtype(dtype):
            return QVariant.DateTime
        if pd.api.types.is_datetime64_dtype(dtype):
            return QVariant.DateTime
        if pd.api.types.is_timedelta64_dtype(dtype):
            # store as string "HH:MM:SS" fallback
            return QVariant.String
    except Exception:
        pass
    # default to string
    return QVariant.String


def _fields_from_dataframe(df, drop_cols=None) -> QgsFields:
    """Build QgsFields from DataFrame dtypes."""
    drop_cols = set(drop_cols or [])
    fields = QgsFields()
    for name, dtype in df.dtypes.items():
        if name in drop_cols:
            continue
        vtype = _qvariant_type_from_dtype(dtype)
        fields.append(QgsField(name, vtype))
    return fields


# ---------- main function you'll call inside processAlgorithm ----------

def dataframeToQgsLayer(
    df,
    x_col: str,
    y_col: str,
    *,
    crs: QgsCoordinateReferenceSystem,
    algorithm,            # `self` inside a QgsProcessingAlgorithm
    parameters: dict,
    context,
    feedback,
    sink_param_name: str = "OUTPUT",
    z_col: str = None,
    m_col: str = None,
    include_coords_in_attrs: bool = False,
):
    """
    Write a pandas DataFrame to a point feature sink (QgsProcessingParameterFeatureSink).

    Params
    ------
    df : pandas.DataFrame                  Data with coordinate columns.
    x_col, y_col : str                     Column names for X/Easting/Longitude and Y/Northing/Latitude.
    crs : QgsCoordinateReferenceSystem     CRS of the coordinates (e.g., QgsCoordinateReferenceSystem('EPSG:4326')).
    algorithm : QgsProcessingAlgorithm     Use `self` from inside processAlgorithm.
    parameters, context, feedback          Standard Processing plumbing.
    sink_param_name : str                  Name of your sink output parameter (default "OUTPUT").
    z_col, m_col : str | None              Optional Z and M columns for 3D/M points.
    include_coords_in_attrs : bool         If False, x/y/z/m are not written as attributes.

    Returns
    -------
    (sink, sink_id)                        The created sink and its ID. Also returns feature count via feedback.
    """
    import pandas as pd
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas.DataFrame")

    # Make a working copy; optionally drop coordinate columns from attributes
    attr_df = df.copy()
    drop_cols = []
    for col in [x_col, y_col, z_col, m_col]:
        if col and not include_coords_in_attrs:
            drop_cols.append(col)

    fields = _fields_from_dataframe(attr_df, drop_cols=drop_cols)

    # Geometry type (2D/3D/M)
    has_z = z_col is not None and z_col in df.columns
    has_m = m_col is not None and m_col in df.columns
    if has_z and has_m:
        wkb = QgsWkbTypes.PointZM
    elif has_z:
        wkb = QgsWkbTypes.PointZ
    elif has_m:
        wkb = QgsWkbTypes.PointM
    else:
        wkb = QgsWkbTypes.Point

    # Create the sink
    sink, sink_id = algorithm.parameterAsSink(
        parameters,
        sink_param_name,
        context,
        fields,
        wkb,
        crs
    )
    if sink is None:
        raise QgsProcessingException("Could not create feature sink. Check output parameter and inputs.")

    total = len(df)
    feedback.pushInfo(f"Writing {total} features…")

    # Precompute attribute column order
    attr_columns = [f.name() for f in fields]

    # Iterate rows and write features
    for i, (_idx, row) in enumerate(df.iterrows(), start=1):
        if feedback.isCanceled():
            break

        # Build point geometry
        x = row[x_col]
        y = row[y_col]

        # skip rows with missing coords
        if pd.isna(x) or pd.isna(y):
            continue

        if has_z and not pd.isna(row[z_col]) and has_m and not pd.isna(row[m_col]):
            pt = QgsPoint(float(x), float(y), float(row[z_col]), float(row[m_col]))
        elif has_z and not pd.isna(row[z_col]):
            pt = QgsPoint(float(x), float(y), float(row[z_col]))
        elif has_m and not pd.isna(row[m_col]):
            # PointM constructor: setZValue not needed; M is the 4th ordinate
            pt = QgsPoint(float(x), float(y))
            pt.setM(float(row[m_col]))
        else:
            pt = QgsPointXY(float(x), float(y))

        feat = QgsFeature(fields)
        feat.setGeometry(QgsGeometry.fromPoint(pt) if isinstance(pt, QgsPoint) else QgsGeometry.fromPointXY(pt))

        # Attributes in the same order as fields
        attrs = []
        for col in attr_columns:
            val = row[col] if col in row else None
            # Pandas NaN -> None
            if pd.isna(val):
                val = None
            # Convert numpy types to Python scalars to avoid QVariant issues
            try:
                import numpy as np
                if isinstance(val, (np.generic,)):
                    val = val.item()
            except Exception:
                pass
            # Convert pandas Timestamp to Python datetime
            if hasattr(val, "to_pydatetime"):
                try:
                    val = val.to_pydatetime()
                except Exception:
                    val = str(val)
            attrs.append(val)
        feat.setAttributes(attrs)

        sink.addFeature(feat, QgsFeature.FastInsert)

        if i % 1000 == 0:
            feedback.setProgress(int(100.0 * i / max(total, 1)))

    feedback.pushInfo("Done.")
    feedback.setProgress(100)
    return sink, sink_id
