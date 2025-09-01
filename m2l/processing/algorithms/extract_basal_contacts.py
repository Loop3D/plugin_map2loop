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
    QgsProcessingParameterField,
    QgsProcessingParameterMatrix,
    QgsSettings
)
# Internal imports
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame, GeoDataFrameToQgsLayer
from map2loop.contact_extractor import ContactExtractor


class BasalContactsAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm to create basal contacts."""
    
    
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_FAULTS = 'FAULTS'
    INPUT_STRATI_COLUMN = 'STRATIGRAPHIC_COLUMN'
    INPUT_IGNORE_UNITS = 'IGNORE_UNITS'
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
                "FAULTS",
                [QgsProcessing.TypeVectorLine],
                optional=True,
            )
        )
        strati_settings = QgsSettings()
        last_strati_column = strati_settings.value("m2l/strati_column", "")
        self.addParameter(
            QgsProcessingParameterMatrix(
                name=self.INPUT_STRATI_COLUMN,
                description="Stratigraphic Order",
                headers=["Unit"],
                numberRows=0,
                defaultValue=last_strati_column
            )
        )
        ignore_settings = QgsSettings()
        last_ignore_units = ignore_settings.value("m2l/ignore_units", "")
        self.addParameter(
            QgsProcessingParameterMatrix(
                self.INPUT_IGNORE_UNITS,
                "Unit(s) to ignore",
                headers=["Unit"],
                defaultValue=last_ignore_units,
                optional=True
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

        feedback.pushInfo("Loading data...")
        geology = self.parameterAsVectorLayer(parameters, self.INPUT_GEOLOGY, context)
        faults = self.parameterAsVectorLayer(parameters, self.INPUT_FAULTS, context)
        strati_column = self.parameterAsMatrix(parameters, self.INPUT_STRATI_COLUMN, context)
        ignore_units = self.parameterAsMatrix(parameters, self.INPUT_IGNORE_UNITS, context) 
        # if strati_column and strati_column.strip():
        #     strati_column = [unit.strip() for unit in strati_column.split(',')]
        # Save stratigraphic column settings
        strati_column_settings = QgsSettings()
        strati_column_settings.setValue('m2l/strati_column', strati_column)

        ignore_settings = QgsSettings()
        ignore_settings.setValue("m2l/ignore_units", ignore_units)

        unit_name_field = self.parameterAsString(parameters, 'UNIT_NAME_FIELD', context)
        
        geology = qgsLayerToGeoDataFrame(geology)
        mask = ~geology['Formation'].astype(str).str.strip().isin(ignore_units)
        geology = geology[mask].reset_index(drop=True)
        
        faults = qgsLayerToGeoDataFrame(faults) if faults else None
        if unit_name_field != 'UNITNAME' and unit_name_field in geology.columns:
            geology = geology.rename(columns={unit_name_field: 'UNITNAME'})

        feedback.pushInfo("Extracting Basal Contacts...")
        contact_extractor = ContactExtractor(geology, faults)
        basal_contacts = contact_extractor.extract_basal_contacts(strati_column)
        
        feedback.pushInfo("Exporting Basal Contacts Layer...")
        basal_contacts = GeoDataFrameToQgsLayer(
            self, 
            contact_extractor.basal_contacts,
            parameters=parameters,
            context=context,
            output_key=self.OUTPUT,
            feedback=feedback,
            )
        return {self.OUTPUT: basal_contacts}

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # BasalContactsAlgorithm()
