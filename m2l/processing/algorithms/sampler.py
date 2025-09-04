"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# Python imports
from typing import Any, Optional
from qgis.PyQt.QtCore import QMetaType
from osgeo import gdal
import pandas as pd

# QGIS imports
from qgis.core import (
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem
)
# Internal imports
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame
from map2loop.sampler import SamplerDecimator, SamplerSpacing


class SamplerAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm for sampling."""

    INPUT_SAMPLER_TYPE = 'SAMPLER_TYPE'
    INPUT_DTM = 'DTM'
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_SPATIAL_DATA = 'SPATIAL_DATA'
    INPUT_DECIMATION = 'DECIMATION'
    INPUT_SPACING = 'SPACING'

    OUTPUT = "SAMPLED_CONTACTS"

    def name(self) -> str:
        """Return the algorithm name."""
        return "sampler"

    def displayName(self) -> str:
        """Return the algorithm display name."""
        return "Loop3d: Sampler"

    def group(self) -> str:
        """Return the algorithm group name."""
        return "Loop3d"

    def groupId(self) -> str:
        """Return the algorithm group ID."""
        return "Loop3d"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize the algorithm parameters."""
        
        
        self.addParameter(
            QgsProcessingParameterEnum(
                self.INPUT_SAMPLER_TYPE,
                "SAMPLER_TYPE",
                ["Decimator", "Spacing"],
                defaultValue=0
            )
        )
        
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_DTM,
                "DTM",
                [QgsProcessing.TypeRaster],
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_GEOLOGY,
                "GEOLOGY",
                [QgsProcessing.TypeVectorPolygon],
                optional=True,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_SPATIAL_DATA,
                "SPATIAL_DATA",
                [QgsProcessing.TypeVectorAnyGeometry],
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.INPUT_DECIMATION,
                "DECIMATION",
                QgsProcessingParameterNumber.Integer,
                defaultValue=1,
                optional=True,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
                self.INPUT_SPACING,
                "SPACING",
                QgsProcessingParameterNumber.Double,
                defaultValue=200.0,
                optional=True,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Sampled Points",
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:

        dtm = self.parameterAsRasterLayer(parameters, self.INPUT_DTM, context)
        geology = self.parameterAsVectorLayer(parameters, self.INPUT_GEOLOGY, context)
        spatial_data = self.parameterAsVectorLayer(parameters, self.INPUT_SPATIAL_DATA, context)
        decimation = self.parameterAsInt(parameters, self.INPUT_DECIMATION, context)
        spacing = self.parameterAsDouble(parameters, self.INPUT_SPACING, context)
        sampler_type_index = self.parameterAsEnum(parameters, self.INPUT_SAMPLER_TYPE, context)
        sampler_type = ["Decimator", "Spacing"][sampler_type_index]
        
        # Convert geology layers to GeoDataFrames
        geology = qgsLayerToGeoDataFrame(geology)
        spatial_data_gdf = qgsLayerToGeoDataFrame(spatial_data)
        dtm_gdal = gdal.Open(dtm.source())
        
        if sampler_type == "Decimator":
            feedback.pushInfo("Sampling...")
            sampler = SamplerDecimator(decimation=decimation, dtm_data=dtm_gdal, geology_data=geology)
            samples = sampler.sample(spatial_data_gdf)
            
        if sampler_type == "Spacing":
            feedback.pushInfo("Sampling...")
            sampler = SamplerSpacing(spacing=spacing, dtm_data=dtm_gdal, geology_data=geology)
            samples = sampler.sample(spatial_data_gdf)
        
        fields = QgsFields()
        fields.append(QgsField("ID", QMetaType.Type.QString))
        fields.append(QgsField("X", QMetaType.Type.Float))
        fields.append(QgsField("Y", QMetaType.Type.Float))
        fields.append(QgsField("Z", QMetaType.Type.Float))
        fields.append(QgsField("featureId", QMetaType.Type.QString))

        crs = None
        if spatial_data_gdf is not None and spatial_data_gdf.crs is not None:
            crs = QgsCoordinateReferenceSystem.fromWkt(spatial_data_gdf.crs.to_wkt())

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.PointZ if 'Z' in (samples.columns if samples is not None else []) else QgsWkbTypes.Point,
            crs
        )

        if samples is not None and not samples.empty:
            for index, row in samples.iterrows():
                feature = QgsFeature(fields)
                
                # decimator has z values
                if 'Z' in samples.columns and pd.notna(row.get('Z')):
                    wkt = f"POINT Z ({row['X']} {row['Y']} {row['Z']})"
                    feature.setGeometry(QgsGeometry.fromWkt(wkt))
                else:
                    #spacing has no z values
                    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(row['X'], row['Y'])))
                
                feature.setAttributes([
                    str(row.get('ID', '')),
                    float(row.get('X', 0)),
                    float(row.get('Y', 0)),
                    float(row.get('Z', 0)) if pd.notna(row.get('Z')) else 0.0,
                    str(row.get('featureId', ''))
                ])
                
                sink.addFeature(feature)

        return {self.OUTPUT: dest_id}

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # SamplerAlgorithm()