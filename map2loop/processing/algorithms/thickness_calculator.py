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
from map2loop.map2loop.thickness_calculator import InterpolatedStructure, StructuralPoint


class ThicknessCalculatorAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm for thickness calculations."""

    INPUT_THICKNESS_CALCULATOR_TYPE = 'THICKNESS_CALCULATOR_TYPE'
    INPUT_DTM = 'DTM'
    INPUT_BOUNDING_BOX = 'BOUNDING_BOX'
    INPUT_MAX_LINE_LENGTH = 'MAX_LINE_LENGTH'
    INPUT_UNITS = 'UNITS'
    INPUT_STRATI_COLUMN = 'STRATIGRAPHIC_COLUMN'
    INPUT_BASAL_CONTACTS = 'BASAL_CONTACTS'
    INPUT_STRUCTURE_DATA = 'STRUCTURE_DATA'
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_SAMPLED_CONTACTS = 'SAMPLED_CONTACTS'

    OUTPUT = "THICKNESS"

    def name(self) -> str:
        """Return the algorithm name."""
        return "thickness_calculator"

    def displayName(self) -> str:
        """Return the algorithm display name."""
        return "Loop3d: Thickness Calculator"

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
                self.INPUT_THICKNESS_CALCULATOR_TYPE,
                "Thickness Calculator Type",
                [QgsProcessing.TypeVectorPoint],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_BASAL_CONTACTS,
                "Basal Contacts",
                [QgsProcessing.TypeVectorPoint],
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
                "Thickness",
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



class InterpolatedStructureAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm for thickness calculations."""


    INPUT_UNITS = 'UNITS'
    INPUT_STRATI_COLUMN = 'STRATIGRAPHIC_COLUMN'
    INPUT_BASAL_CONTACTS = 'BASAL_CONTACTS'
    INPUT_STRUCTURE_DATA = 'STRUCTURE_DATA'
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_SAMPLED_CONTACTS = 'SAMPLED_CONTACTS'

    OUTPUT = "THICKNESS"

    def name(self) -> str:
        """Return the algorithm name."""
        return "thickness_calculator"

    def displayName(self) -> str:
        """Return the algorithm display name."""
        return "Loop3d: Thickness Calculator"

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
    


class StructuralPointAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm for thickness calculations."""


    INPUT_UNITS = 'UNITS'
    INPUT_STRATI_COLUMN = 'STRATIGRAPHIC_COLUMN'
    INPUT_BASAL_CONTACTS = 'BASAL_CONTACTS'
    INPUT_STRUCTURE_DATA = 'STRUCTURE_DATA'
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_SAMPLED_CONTACTS = 'SAMPLED_CONTACTS'

    OUTPUT = "THICKNESS"

    def name(self) -> str:
        """Return the algorithm name."""
        return "thickness_calculator"

    def displayName(self) -> str:
        """Return the algorithm display name."""
        return "Loop3d: Thickness Calculator"

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