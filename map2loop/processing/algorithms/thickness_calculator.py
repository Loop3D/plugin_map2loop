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
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterField,
    QgsProcessingParameterMatrix
)
# Internal imports
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame, GeoDataFrameToQgsLayer, qgsLayerToDataFrame, dataframeToQgsLayer
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
            QgsProcessingParameterEnum(
                self.INPUT_THICKNESS_CALCULATOR_TYPE,
                "Thickness Calculator Type",
                options=['InterpolatedStructure','StructuralPoint'], 
                allowMultiple=False,
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
            QgsProcessingParameterEnum(
                self.INPUT_BOUNDING_BOX,
                "Bounding Box",
                options=['minx','miny','maxx','maxy'], 
                allowMultiple=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.INPUT_MAX_LINE_LENGTH,
                "Max Line Length",
                minValue=0,
                defaultValue=1000
            )
        )   
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_UNITS,
                "Units",
                [QgsProcessing.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_BASAL_CONTACTS,
                "Basal Contacts",
                [QgsProcessing.TypeVectorLine],
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
            QgsProcessingParameterMatrix(
                name=self.INPUT_STRATI_COLUMN,
                description="Stratigraphic Order",
                headers=["Unit"],
                numberRows=0,
                defaultValue=[]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_SAMPLED_CONTACTS,
                "SAMPLED_CONTACTS",
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_STRUCTURE_DATA,
                "STRUCTURE_DATA",
                [QgsProcessing.TypeVectorPoint],
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

        feedback.pushInfo("Initialising Thickness Calculation Algorithm...")
        thickness_type = self.parameterAsEnum(parameters, self.INPUT_THICKNESS_CALCULATOR_TYPE, context)
        dtm_data = self.parameterAsSource(parameters, self.INPUT_DTM, context)
        bounding_box = self.parameterAsEnum(parameters, self.INPUT_BOUNDING_BOX, context)
        max_line_length = self.parameterAsNumber(parameters, self.INPUT_MAX_LINE_LENGTH, context)
        units = self.parameterAsSource(parameters, self.INPUT_UNITS, context)
        basal_contacts = self.parameterAsSource(parameters, self.INPUT_BASAL_CONTACTS, context)
        geology_data = self.parameterAsSource(parameters, self.INPUT_GEOLOGY, context)
        stratigraphic_order = self.parameterAsMatrix(parameters, self.INPUT_STRATI_COLUMN, context)
        structure_data = self.parameterAsSource(parameters, self.INPUT_STRUCTURE_DATA, context)
        sampled_contacts = self.parameterAsSource(parameters, self.INPUT_SAMPLED_CONTACTS, context)

        # convert layers to dataframe or geodataframe
        geology_data = qgsLayerToGeoDataFrame(geology_data)
        units = qgsLayerToDataFrame(units)
        basal_contacts = qgsLayerToGeoDataFrame(basal_contacts)
        structure_data = qgsLayerToDataFrame(structure_data)
        sampled_contacts = qgsLayerToDataFrame(sampled_contacts)

        feedback.pushInfo("Calculating unit thicknesses...")
        
        if thickness_type == "InterpolatedStructure":
            thickness_calculator = InterpolatedStructure(
                dtm_data=dtm_data,
                bounding_box=bounding_box,
            )
            thickness_calculator.compute(
                units, 
                stratigraphic_order, 
                basal_contacts, 
                structure_data, 
                geology_data, 
                sampled_contacts
            )

        if thickness_type == "StructuralPoint":
            thickness_calculator = StructuralPoint(
                dtm_data=dtm_data,
                bounding_box=bounding_box,
                max_line_length=max_line_length,
            )
            thickness_calculator.compute(
                units,
                stratigraphic_order,
                basal_contacts,
                structure_data,
                geology_data,
                sampled_contacts
            )

        #TODO: convert thicknesses dataframe to qgs layer
        thicknesses = dataframeToQgsLayer(
            self, 
            # contact_extractor.basal_contacts,
            parameters=parameters,
            context=context,
            feedback=feedback,
            )
        
        return {self.OUTPUT: thicknesses[1]}

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # BasalContactsAlgorithm()