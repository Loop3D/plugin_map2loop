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
    QgsProcessingParameterField,
    QgsVectorLayer
)
# Internal imports
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame, GeoDataFrameToQgsLayer
from map2loop.contact_extractor import ContactExtractor

import logging
import traceback

class ContactsAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm to extract contacts."""
    
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_FAULTS = 'FAULTS'
    OUTPUT = "CONTACTS"

    def name(self) -> str:
        """Return the algorithm name."""
        return "contacts"

    def displayName(self) -> str:
        """Return the algorithm display name."""
        return "Extract Contacts"

    def group(self) -> str:
        """Return the algorithm group name."""
        return "Contact Extractors"

    def groupId(self) -> str:
        """Return the algorithm group ID."""
        return "Contact_Extractors"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize the algorithm."""
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_GEOLOGY,
                "Geology polygons",
                [QgsProcessing.TypeVectorPolygon],
                optional=False
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                'UNIT_NAME_FIELD',
                'Unit Name Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.String,
                defaultValue='unitname'
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_FAULTS,
                "Faults",
                [QgsProcessing.TypeVectorLine],
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Contacts",
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:

        feedback.pushInfo("Loading data...")
        geology = self.parameterAsVectorLayer(parameters, self.INPUT_GEOLOGY, context)
        faults = self.parameterAsVectorLayer(parameters, self.INPUT_FAULTS, context)

        unit_name_field = self.parameterAsString(parameters, 'UNIT_NAME_FIELD', context)
        
        geology = qgsLayerToGeoDataFrame(geology)
        
        faults = qgsLayerToGeoDataFrame(faults) if faults else None
        if unit_name_field != 'UNITNAME' and unit_name_field in geology.columns:
            geology = geology.rename(columns={unit_name_field: 'UNITNAME'})

        contact_extractor = ContactExtractor(geology, faults)
        all_contacts = contact_extractor.extract_all_contacts()

        feedback.pushInfo("Exporting Contacts Layer...")
        contacts_layer = GeoDataFrameToQgsLayer(
            self, 
            all_contacts,
            parameters=parameters,
            context=context,
            output_key=self.OUTPUT,
            feedback=feedback,
        )
        return {self.OUTPUT: contacts_layer}

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # ContactsAlgorithm()
