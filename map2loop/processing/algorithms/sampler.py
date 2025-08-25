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

# QGIS imports
from qgis import processing
from qgis.core import (
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber
)
# Internal imports
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame, GeoDataFrameToQgsLayer 
from map2loop.map2loop.sampler import SamplerDecimator, SamplerSpacing


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
        return "loop3d"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize the algorithm parameters."""
        
        
        self.addParameter(
            QgsProcessingParameterString(
                self.INPUT_SAMPLER_TYPE,
                "SAMPLER_TYPE",
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_DTM,
                "DTM",
                [QgsProcessing.TypeVectorRaster],
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
                optional=True,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
                self.INPUT_SPACING,
                "SPACING",
                optional=True,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Sampled Contacts",
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:

        dtm = self.parameterAsSource(parameters, self.INPUT_DTM, context)
        geology = self.parameterAsSource(parameters, self.INPUT_GEOLOGY, context)
        spatial_data = self.parameterAsSource(parameters, self.INPUT_SPATIAL_DATA, context)
        decimation = self.parameterAsSource(parameters, self.INPUT_DECIMATION, context)
        spacing = self.parameterAsSource(parameters, self.INPUT_SPACING, context)
        sampler_type = self.parameterAsString(parameters, self.INPUT_SAMPLER_TYPE, context)
        
        # Convert geology layers to GeoDataFrames
        geology = qgsLayerToGeoDataFrame(geology)
        spatial_data = qgsLayerToGeoDataFrame(spatial_data)
        
        if sampler_type == "decimator":
            feedback.pushInfo("Sampling...")
            sampler = SamplerDecimator(decimation=decimation, dtm_data=dtm, geology_data=geology, feedback=feedback)
            samples = sampler.sample(spatial_data)
            
        if sampler_type == "spacing":
            feedback.pushInfo("Sampling...")
            sampler = SamplerSpacing(spacing=spacing, dtm_data=dtm, geology_data=geology, feedback=feedback)
            samples = sampler.sample(spatial_data)

        #TODO: convert sample to qgis layer
        # samples = qgs
        return {self.OUTPUT: samples}

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # SamplerAlgorithm()