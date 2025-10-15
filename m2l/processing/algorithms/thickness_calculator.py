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
import pandas as pd

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
    QgsProcessingParameterMatrix, 
    QgsSettings,
    QgsProcessingParameterRasterLayer,
)
# Internal imports
from ...main.vectorLayerWrapper import (
    qgsLayerToGeoDataFrame, 
    GeoDataFrameToQgsLayer, 
    qgsLayerToDataFrame, 
    dataframeToQgsLayer, 
    qgsRasterToGdalDataset,
    matrixToDict,
    dataframeToQgsTable
    )
from map2loop.thickness_calculator import InterpolatedStructure, StructuralPoint


class ThicknessCalculatorAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm for thickness calculations."""

    INPUT_THICKNESS_CALCULATOR_TYPE = 'THICKNESS_CALCULATOR_TYPE'
    INPUT_DTM = 'DTM'
    INPUT_BOUNDING_BOX_TYPE = 'BOUNDING_BOX_TYPE'
    INPUT_BOUNDING_BOX = 'BOUNDING_BOX'
    INPUT_MAX_LINE_LENGTH = 'MAX_LINE_LENGTH'
    INPUT_STRATI_COLUMN = 'STRATIGRAPHIC_COLUMN'
    INPUT_BASAL_CONTACTS = 'BASAL_CONTACTS'
    INPUT_STRUCTURE_DATA = 'STRUCTURE_DATA'
    INPUT_DIPDIR_FIELD = 'DIPDIR_FIELD'
    INPUT_DIP_FIELD = 'DIP_FIELD'
    INPUT_GEOLOGY = 'GEOLOGY'
    INPUT_THICKNESS_ORIENTATION_TYPE = 'THICKNESS_ORIENTATION_TYPE'
    INPUT_UNIT_NAME_FIELD = 'UNIT_NAME_FIELD'
    INPUT_SAMPLED_CONTACTS = 'SAMPLED_CONTACTS'
    INPUT_STRATIGRAPHIC_COLUMN_LAYER = 'STRATIGRAPHIC_COLUMN_LAYER'

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
        return "Loop3d"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize the algorithm parameters."""
        
        self.addParameter(
            QgsProcessingParameterEnum(
                self.INPUT_THICKNESS_CALCULATOR_TYPE,
                "Thickness Calculator Type",
                options=['InterpolatedStructure','StructuralPoint'], 
                allowMultiple=False,
                defaultValue='InterpolatedStructure'
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_DTM,
                "DTM (InterpolatedStructure)",
                [QgsProcessing.TypeRaster],
                optional=True,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterEnum(
                self.INPUT_BOUNDING_BOX_TYPE,
                "Bounding Box Type",
                options=['Extract from geology layer', 'User defined'],
                allowMultiple=False,
                defaultValue=1
            )
        )
        
        bbox_settings = QgsSettings()
        last_bbox = bbox_settings.value("m2l/bounding_box", "")
        self.addParameter(
            QgsProcessingParameterMatrix(
                self.INPUT_BOUNDING_BOX,
                description="Static Bounding Box",
                headers=['minx','miny','maxx','maxy'],
                numberRows=1,
                defaultValue=last_bbox,
                optional=True
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
                self.INPUT_BASAL_CONTACTS,
                "Basal Contacts",
                [QgsProcessing.TypeVectorLine],
                defaultValue='Basal Contacts',
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
            QgsProcessingParameterField(
                'UNIT_NAME_FIELD',
                'Unit Name Field e.g. Formation',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.String,
                defaultValue='Formation'
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                'STRATIGRAPHIC_COLUMN_LAYER',
                'Stratigraphic Column Layer (from sorter)',
                [QgsProcessing.TypeVector],
                optional=True
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
                defaultValue=last_strati_column,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_SAMPLED_CONTACTS,
                "Sampled Contacts",
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_STRUCTURE_DATA,
                "Orientation Data",
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                'THICKNESS_ORIENTATION_TYPE',
                'Thickness Orientation Type',
                options=['Dip Direction', 'Strike'],
                defaultValue=0  # Default to Dip Direction
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.INPUT_DIPDIR_FIELD,
                "Dip Direction Column",
                parentLayerParameterName=self.INPUT_STRUCTURE_DATA,
                type=QgsProcessingParameterField.Numeric,
                defaultValue='DIPDIR'
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.INPUT_DIP_FIELD,
                "Dip Column",
                parentLayerParameterName=self.INPUT_STRUCTURE_DATA,
                type=QgsProcessingParameterField.Numeric,
                defaultValue='DIP'
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
        thickness_type_index = self.parameterAsEnum(parameters, self.INPUT_THICKNESS_CALCULATOR_TYPE, context)
        thickness_type = ['InterpolatedStructure', 'StructuralPoint'][thickness_type_index]
        dtm_data = self.parameterAsRasterLayer(parameters, self.INPUT_DTM, context)
        bounding_box_type = self.parameterAsEnum(parameters, self.INPUT_BOUNDING_BOX_TYPE, context)
        max_line_length = self.parameterAsSource(parameters, self.INPUT_MAX_LINE_LENGTH, context)
        basal_contacts = self.parameterAsSource(parameters, self.INPUT_BASAL_CONTACTS, context)
        geology_data = self.parameterAsSource(parameters, self.INPUT_GEOLOGY, context)
        structure_data = self.parameterAsSource(parameters, self.INPUT_STRUCTURE_DATA, context)
        thickness_orientation_type = self.parameterAsEnum(parameters, self.INPUT_THICKNESS_ORIENTATION_TYPE, context)
        is_strike = (thickness_orientation_type == 1)
        structure_dipdir_field = self.parameterAsString(parameters, self.INPUT_DIPDIR_FIELD, context)
        structure_dip_field = self.parameterAsString(parameters, self.INPUT_DIP_FIELD, context)
        sampled_contacts = self.parameterAsSource(parameters, self.INPUT_SAMPLED_CONTACTS, context)
        unit_name_field = self.parameterAsString(parameters, self.INPUT_UNIT_NAME_FIELD, context)

        if bounding_box_type == 0:
            geology_layer = self.parameterAsVectorLayer(parameters, self.INPUT_GEOLOGY, context)
            extent = geology_layer.extent()
            bounding_box = {
                'minx': extent.xMinimum(),
                'miny': extent.yMinimum(),
                'maxx': extent.xMaximum(),
                'maxy': extent.yMaximum()
            }
            feedback.pushInfo("Using bounding box from geology layer")
        else:
            static_bbox_matrix = self.parameterAsMatrix(parameters, self.INPUT_BOUNDING_BOX, context)
            if not static_bbox_matrix or len(static_bbox_matrix) == 0:
                raise QgsProcessingException("Bounding box is required")
            
            bounding_box = matrixToDict(static_bbox_matrix)
            
            bbox_settings = QgsSettings()
            bbox_settings.setValue("m2l/bounding_box", static_bbox_matrix)
            feedback.pushInfo("Using bounding box from user input")

        stratigraphic_column_source = self.parameterAsSource(parameters, self.INPUT_STRATIGRAPHIC_COLUMN_LAYER, context)
        stratigraphic_order = []
        if stratigraphic_column_source is not None:
            ordered_pairs =[]
            for feature in stratigraphic_column_source.getFeatures():
                order = feature.attribute('order')
                unit_name = feature.attribute('unit_name')
                ordered_pairs.append((order, unit_name))
            ordered_pairs.sort(key=lambda x: x[0])
            stratigraphic_order = [pair[1] for pair in ordered_pairs]
            feedback.pushInfo(f"DEBUG: parameterAsVectorLayer Stratigraphic order: {stratigraphic_order}")
        else:
            matrix_stratigraphic_order = self.parameterAsMatrix(parameters, self.INPUT_STRATI_COLUMN, context)
            if matrix_stratigraphic_order:
                stratigraphic_order = [str(row) for row in matrix_stratigraphic_order if row]
            else:
                raise QgsProcessingException("Stratigraphic column layer is required")
        if stratigraphic_order:
            matrix = [[unit] for unit in stratigraphic_order]
            strati_column_settings = QgsSettings()
            strati_column_settings.setValue('m2l/strati_column', matrix)
        # convert layers to dataframe or geodataframe
        units = qgsLayerToDataFrame(geology_data)
        geology_data = qgsLayerToGeoDataFrame(geology_data)
        basal_contacts = qgsLayerToGeoDataFrame(basal_contacts)
        structure_data = qgsLayerToDataFrame(structure_data)
        rename_map = {}
        missing_fields = []
        if unit_name_field != 'UNITNAME' and unit_name_field in geology_data.columns:
            geology_data = geology_data.rename(columns={unit_name_field: 'UNITNAME'})
        units_unique = units.drop_duplicates(subset=[unit_name_field]).reset_index(drop=True)
        units = pd.DataFrame({'name': units_unique[unit_name_field]})
        if structure_data is not None:
            if structure_dipdir_field:
                if structure_dipdir_field in structure_data.columns:
                    rename_map[structure_dipdir_field] = 'DIPDIR'
                else:
                    missing_fields.append(structure_dipdir_field)
            if structure_dip_field:
                if structure_dip_field in structure_data.columns:
                    rename_map[structure_dip_field] = 'DIP'
                else:
                    missing_fields.append(structure_dip_field)
            if missing_fields:
                raise QgsProcessingException(
                    f"Orientation data missing required field(s): {', '.join(missing_fields)}"
                )
            if rename_map:
                structure_data = structure_data.rename(columns=rename_map)
        
        sampled_contacts = qgsLayerToDataFrame(sampled_contacts)
        sampled_contacts['X'] = sampled_contacts['X'].astype(float)
        sampled_contacts['Y'] = sampled_contacts['Y'].astype(float)
        sampled_contacts['Z'] = sampled_contacts['Z'].astype(float)
        dtm_data = qgsRasterToGdalDataset(dtm_data)
        if thickness_type == "InterpolatedStructure":
            thickness_calculator = InterpolatedStructure(
                dtm_data=dtm_data,
                bounding_box=bounding_box,
                is_strike=is_strike
            )
            thicknesses = thickness_calculator.compute(
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
                is_strike=is_strike
            )
            thicknesses =thickness_calculator.compute(
                units,
                stratigraphic_order,
                basal_contacts,
                structure_data,
                geology_data,
                sampled_contacts
            )

        thicknesses = thicknesses[
            ["name","ThicknessMean","ThicknessMedian", "ThicknessStdDev"] 
        ].copy()
        
        feedback.pushInfo("Exporting Thickness Table...")
        thicknesses = dataframeToQgsTable(
            self,
            thicknesses,
            parameters=parameters,
            context=context,
            feedback=feedback,
            param_name=self.OUTPUT
        )

        return {self.OUTPUT: thicknesses[1]}

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # ThicknessCalculatorAlgorithm()
