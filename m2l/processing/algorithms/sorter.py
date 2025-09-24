from typing import Any, Optional
from osgeo import gdal
import pandas as pd
import json

from PyQt5.QtCore import QVariant
from qgis import processing
from qgis.core import (
    QgsFeatureSink,
    QgsFields, 
    QgsField, 
    QgsFeature, 
    QgsGeometry,
    QgsRasterLayer,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterMatrix,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsSettings
)

# ────────────────────────────────────────────────
#  map2loop sorters
# ────────────────────────────────────────────────
from map2loop.sorter import (
    SorterAlpha,
    SorterAgeBased,
    SorterMaximiseContacts,
    SorterObservationProjections,
    SorterUseNetworkX,
    SorterUseHint,      # kept for backwards compatibility
)
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame, qvariantToFloat

# a lookup so we don’t need a giant if/else block
SORTER_LIST = {
    "Age‐based": SorterAgeBased,
    "NetworkX topological": SorterUseNetworkX,
    "Hint (deprecated)": SorterUseHint,
    "Adjacency α": SorterAlpha,
    "Maximise contacts": SorterMaximiseContacts,
    "Observation projections": SorterObservationProjections,
}

class StratigraphySorterAlgorithm(QgsProcessingAlgorithm):
    """
    Creates a one-column ‘stratigraphic column’ table ordered
    by the selected map2loop sorter.
    """
    METHOD = "METHOD"
    INPUT_GEOLOGY = "INPUT_GEOLOGY"
    INPUT_STRUCTURE = "INPUT_STRUCTURE"
    INPUT_DTM = "INPUT_DTM"
    INPUT_STRATI_COLUMN = "INPUT_STRATI_COLUMN"
    SORTING_ALGORITHM  = "SORTING_ALGORITHM"
    OUTPUT = "OUTPUT"
    CONTACTS_LAYER = "CONTACTS_LAYER"

    # ----------------------------------------------------------
    #  Metadata
    # ----------------------------------------------------------
    def name(self) -> str:
        return "loop_sorter"

    def displayName(self) -> str:
        return "Loop3d: Stratigraphic sorter"

    def group(self) -> str:
        return "Loop3d"

    def groupId(self) -> str:
        return "Loop3d"
    
    def updateParameters(self, parameters):
        selected_method = parameters.get(self.METHOD, 0)
        selected_algorithm = parameters.get(self.SORTING_ALGORITHM, 0)

        if selected_method == 0:  # User-Defined selected
            self.parameterDefinition(self.INPUT_STRATI_COLUMN).setMetadata({'widget_wrapper': {'visible': True}})
            self.parameterDefinition(self.SORTING_ALGORITHM).setMetadata({'widget_wrapper': {'visible': False}})
            self.parameterDefinition(self.INPUT_GEOLOGY).setMetadata({'widget_wrapper': {'visible': False}})
        else:  # Automatic selected
            self.parameterDefinition(self.INPUT_GEOLOGY).setMetadata({'widget_wrapper': {'visible': True}})
            self.parameterDefinition(self.SORTING_ALGORITHM).setMetadata({'widget_wrapper': {'visible': True}})
            self.parameterDefinition(self.INPUT_STRATI_COLUMN).setMetadata({'widget_wrapper': {'visible': False}})
            
            # observation projects
            is_observation_projections = selected_algorithm == 5
            self.parameterDefinition(self.INPUT_STRUCTURE).setMetadata({'widget_wrapper': {'visible': is_observation_projections}})
            self.parameterDefinition(self.INPUT_DTM).setMetadata({'widget_wrapper': {'visible': is_observation_projections}})
            self.parameterDefinition('DIP_FIELD').setMetadata({'widget_wrapper': {'visible': is_observation_projections}})
            self.parameterDefinition('DIPDIR_FIELD').setMetadata({'widget_wrapper': {'visible': is_observation_projections}})
            self.parameterDefinition('ORIENTATION_TYPE').setMetadata({'widget_wrapper': {'visible': is_observation_projections}})
                
        return super().updateParameters(parameters)

    # ----------------------------------------------------------
    #  Parameters
    # ----------------------------------------------------------
    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:

         # enum so the user can pick the strategy from a dropdown
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SORTING_ALGORITHM,
                "Sorting strategy",
                options=list(SORTER_LIST.keys()),
                defaultValue="Observation projections",                       # Age-based is safest default
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_GEOLOGY,
                "Geology polygons",
                [QgsProcessing.TypeVectorPolygon],
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                'UNIT_NAME_FIELD',
                'Unit Name Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.Any,
                defaultValue='UNITNAME',
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                'MIN_AGE_FIELD',
                'Minimum Age Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.Any,
                defaultValue='MIN_AGE',
                optional=True
            )
        )
    
        self.addParameter(
            QgsProcessingParameterField(
                'MAX_AGE_FIELD',
                'Maximum Age Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.Any,
                defaultValue='MAX_AGE',
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterField(
                'GROUP_FIELD',
                'Group Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.Any,
                defaultValue='GROUP',
                optional=True
            )
        )

        self.addParameter(
        QgsProcessingParameterFeatureSource(
                self.INPUT_STRUCTURE,
                "Structure",
                [QgsProcessing.TypeVectorPoint],
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                'DIP_FIELD',
                'Dip Field',
                parentLayerParameterName=self.INPUT_STRUCTURE,
                type=QgsProcessingParameterField.Any,
                defaultValue='DIP',
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                'DIPDIR_FIELD',
                'Dip Direction Field',
                parentLayerParameterName=self.INPUT_STRUCTURE,
                type=QgsProcessingParameterField.Any,
                defaultValue='DIPDIR',
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                'ORIENTATION_TYPE',
                'Orientation Type',
                options=['','Dip Direction', 'Strike'],
                defaultValue=0
            )
        )

        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_DTM,
                "DTM",
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "CONTACTS_LAYER",
                "Contacts Layer",
                [QgsProcessing.TypeVectorLine],
                optional=False,
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Stratigraphic column",
            )
        )

        self.addParameter(
            QgsProcessingParameterFileDestination(
                "JSON_OUTPUT",
                "Stratigraphic column json",
                fileFilter="JSON files (*.json)"
            )
        )

    # ----------------------------------------------------------
    #  Core
    # ----------------------------------------------------------
    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:

        algo_index: int = self.parameterAsEnum(parameters, self.SORTING_ALGORITHM, context)
        sorter_cls = list(SORTER_LIST.values())[algo_index]
        contacts_layer = self.parameterAsVectorLayer(parameters, self.CONTACTS_LAYER, context)
        in_layer = self.parameterAsVectorLayer(parameters, self.INPUT_GEOLOGY, context)
        output_file = self.parameterAsFileOutput(parameters, 'JSON_OUTPUT', context)
        
        units_df, relationships_df, contacts_df= build_input_frames(in_layer,contacts_layer, feedback,parameters)

        if sorter_cls == SorterObservationProjections:
            geology_gdf = qgsLayerToGeoDataFrame(in_layer)
            structure = self.parameterAsVectorLayer(parameters, self.INPUT_STRUCTURE, context)
            dtm = self.parameterAsRasterLayer(parameters, self.INPUT_DTM, context)
            if geology_gdf is None or geology_gdf.empty or not structure or not structure.isValid() or not dtm or not dtm.isValid():
                raise QgsProcessingException("Structure and DTM layer are required for observation projections")

            structure_gdf = qgsLayerToGeoDataFrame(structure) if structure else None
            dtm_gdal = gdal.Open(dtm.source()) if dtm is not None and dtm.isValid() else None

            unit_name_field = parameters.get('UNIT_NAME_FIELD', 'UNITNAME') if parameters else 'UNITNAME'
            if unit_name_field != 'UNITNAME' and unit_name_field in geology_gdf.columns:
                geology_gdf = geology_gdf.rename(columns={unit_name_field: 'UNITNAME'})

            dip_field = parameters.get('DIP_FIELD', 'DIP') if parameters else 'DIP'
            if not dip_field:
                raise QgsProcessingException("Dip Field is required")
            if dip_field != 'DIP' and dip_field in structure_gdf.columns:
                structure_gdf = structure_gdf.rename(columns={dip_field: 'DIP'})
            orientation_type = self.parameterAsEnum(parameters, 'ORIENTATION_TYPE', context)
            orientation_type_name = ['','Dip Direction', 'Strike'][orientation_type]
            if not orientation_type_name:
                raise QgsProcessingException("Orientation Type is required")
            dipdir_field = parameters.get('DIPDIR_FIELD', 'DIPDIR') if parameters else 'DIPDIR'
            if not dipdir_field:
                raise QgsProcessingException("Dip Direction Field is required")
            if dipdir_field in structure_gdf.columns:
                if orientation_type_name == 'Strike':
                    structure_gdf['DIPDIR'] = structure_gdf[dipdir_field].apply(
                        lambda val: (val + 90.0) % 360.0 if pd.notnull(val) else val
                    )
                elif orientation_type_name == 'Dip Direction':
                    structure_gdf = structure_gdf.rename(columns={dipdir_field: 'DIPDIR'})
            order = sorter_cls().sort(
                units_df,
                relationships_df,
                contacts_df,
                geology_gdf,
                structure_gdf,
                dtm_gdal
            )
        else:
            order = sorter_cls().sort(
                units_df,
                relationships_df,
                contacts_df
            )

        # 4 ► write an in-memory table with the result
        sink_fields = QgsFields()
        sink_fields.append(QgsField("order", QVariant.Int))
        sink_fields.append(QgsField("unit_name", QVariant.String))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            QgsWkbTypes.NoGeometry,
            in_layer.sourceCrs() if in_layer else None,
        )

        for pos, name in enumerate(order, start=1):
            f = QgsFeature(sink_fields)
            f.setAttributes([pos, name])
            sink.addFeature(f, QgsFeatureSink.FastInsert)
        try:
            with open(output_file, 'w') as f:
                json.dump(order, f)
        except Exception as e:
            with open(output_file, 'w') as f:
                json.dump([], f)

        return {self.OUTPUT: dest_id, 'JSON_OUTPUT': output_file}

    # ----------------------------------------------------------
    def createInstance(self) -> QgsProcessingAlgorithm:
        return StratigraphySorterAlgorithm()


# -------------------------------------------------------------------------
#  Helper stub – you must replace with *your* conversion logic
# -------------------------------------------------------------------------
def build_input_frames(layer: QgsVectorLayer,contacts_layer: QgsVectorLayer, feedback, parameters, user_defined_units=None) -> tuple:
    """
    Placeholder that turns the geology layer (and any other project
    layers) into the four objects required by the sorter.

    Returns
    -------
    (units_df, relationships_df, contacts_df)
    """

    if user_defined_units:
        units_record = []
        for i, row in enumerate(user_defined_units):
            units_record.append(
                dict(
                    layerId=i,
                    name=row[1],
                    minAge=row[2],
                    maxAge=row[3],
                    group=row[4]
                    )
            )
        units_df = pd.DataFrame.from_records(units_record)
    else:
        unit_name_field = parameters.get('UNIT_NAME_FIELD', 'UNITNAME') if parameters else 'UNITNAME'
        min_age_field = parameters.get('MIN_AGE_FIELD', 'MIN_AGE') if parameters else 'MIN_AGE'
        max_age_field = parameters.get('MAX_AGE_FIELD', 'MAX_AGE') if parameters else 'MAX_AGE'
        group_field = parameters.get('GROUP_FIELD', 'GROUP') if parameters else 'GROUP'

        if not layer or not layer.isValid():
            raise QgsProcessingException("No geology layer provided")
        if not unit_name_field:
            raise QgsProcessingException("Unit Name Field is required")
        if not min_age_field:
            raise QgsProcessingException("Minimum Age Field is required")
        if not max_age_field:
            raise QgsProcessingException("Maximum Age Field is required")
        if not group_field:
            raise QgsProcessingException("Group Field is required")

        units_records = []
        for f in layer.getFeatures():
            units_records.append(
                dict(
                    layerId=f.id(),
                    name=f[unit_name_field],          
                    minAge=qvariantToFloat(f, min_age_field),
                    maxAge=qvariantToFloat(f, max_age_field),
                    group=f[group_field],
                )
            )
        units_df = pd.DataFrame.from_records(units_records)

    feedback.pushInfo(f"Units → {len(units_df)}  records")
    # map_data can be mocked if you only use Age-based sorter

    if not contacts_layer or not contacts_layer.isValid():
        raise QgsProcessingException("No contacts layer provided")

    contacts_df = qgsLayerToGeoDataFrame(contacts_layer) if contacts_layer else pd.DataFrame()
    if not contacts_df.empty:
        relationships_df = contacts_df.copy()
        if 'length' in contacts_df.columns:
            relationships_df = relationships_df.drop(columns=['length'])
        if 'geometry' in contacts_df.columns:
            relationships_df = relationships_df.drop(columns=['geometry'])
        feedback.pushInfo(f"Contacts → {len(contacts_df)} records")
        feedback.pushInfo(f"Relationships → {len(relationships_df)} records")
    else:
        relationships_df = pd.DataFrame()

    return units_df, relationships_df, contacts_df