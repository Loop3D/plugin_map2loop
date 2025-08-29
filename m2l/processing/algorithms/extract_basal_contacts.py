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
)
# Internal imports
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame, GeoDataFrameToQgsLayer 
from map2loop.contact_extractor import ContactExtractor


class BasalContactsAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm to create basal contacts."""
    
    
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_FAULTS = 'FAULTS'
    INPUT_STRATI_COLUMN = 'STRATIGRAPHIC_COLUMN'
    OUTPUT = "BASAL_CONTACTS"

    def name(self) -> str:
        """Return the algorithm name."""
        return "basal_contacts"

    def displayName(self) -> str:
        """Return the algorithm display name."""
        return "Loop3d: Basal Contacts"

    def group(self) -> str:
        """Return the algorithm group name."""
        return "Loop3d"

    def groupId(self) -> str:
        """Return the algorithm group ID."""
        return "loop3d"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize the algorithm parameters."""
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_GEOLOGY,
                "GEOLOGY",
                [QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_FAULTS,
                "FAULTS",
                [QgsProcessing.TypeVectorLine],
                optional=True,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_STRATI_COLUMN,
                "STRATIGRAPHIC_COLUMN",
                [QgsProcessing.TypeVectorLine],
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Basal Contacts",
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:

        geology = self.parameterAsSource(parameters, self.INPUT_GEOLOGY, context)
        faults = self.parameterAsSource(parameters, self.INPUT_FAULTS, context)
        strati_column = self.parameterAsSource(parameters, self.INPUT_STRATI_COLUMN, context)
        
        geology = qgsLayerToGeoDataFrame(geology)
        faults = qgsLayerToGeoDataFrame(faults) if faults else None
        
        feedback.pushInfo("Extracting Basal Contacts...")
        contact_extractor = ContactExtractor(geology, faults, feedback)
        contact_extractor.extract_basal_contacts(strati_column)
    
        basal_contacts = GeoDataFrameToQgsLayer(
            self, 
            contact_extractor.basal_contacts,
            parameters=parameters,
            context=context,
            feedback=feedback,
            )
        return {self.OUTPUT: basal_contacts}

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # BasalContactsAlgorithm()
