from typing import Any, Optional
from osgeo import gdal
import pandas as pd

from PyQt5.QtCore import QMetaType
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
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterRasterLayer,
    QgsVectorLayer,
    QgsWkbTypes
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
from map2loop.contact_extractor import ContactExtractor
from ...main.vectorLayerWrapper import qgsLayerToGeoDataFrame

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
        if selected_method == 0:  # User-Defined selected
            self.parameterDefinition(self.INPUT_STRATI_COLUMN).setMetadata({'widget_wrapper': {'visible': True}})
            self.parameterDefinition(self.SORTING_ALGORITHM).setMetadata({'widget_wrapper': {'visible': False}})
            self.parameterDefinition(self.INPUT_GEOLOGY).setMetadata({'widget_wrapper': {'visible': False}})
        else:  # Automatic selected
            self.parameterDefinition(self.INPUT_GEOLOGY).setMetadata({'widget_wrapper': {'visible': True}})
            self.parameterDefinition(self.SORTING_ALGORITHM).setMetadata({'widget_wrapper': {'visible': True}})
            self.parameterDefinition(self.INPUT_STRATI_COLUMN).setMetadata({'widget_wrapper': {'visible': False}})
            
        return super().updateParameters(parameters)

    # ----------------------------------------------------------
    #  Parameters
    # ----------------------------------------------------------
    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:

        self.addParameter(
            QgsProcessingParameterEnum(
                name=self.METHOD,
                description='Select Method',
                options=['User-Defined', 'Automatic'],
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_GEOLOGY,
                "Geology polygons",
                [QgsProcessing.TypeVectorPolygon],
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
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                'MIN_AGE_FIELD',
                'Minimum Age Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.String,
                defaultValue='MIN_AGE',
                optional=True
            )
        )
    
        self.addParameter(
            QgsProcessingParameterField(
                'MAX_AGE_FIELD',
                'Maximum Age Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.String,
                defaultValue='MAX_AGE',
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterField(
                'GROUP_FIELD',
                'Group Field',
                parentLayerParameterName=self.INPUT_GEOLOGY,
                type=QgsProcessingParameterField.String,
                defaultValue='GROUP',
                optional=True
            )
        )
        

        # enum so the user can pick the strategy from a dropdown
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SORTING_ALGORITHM,
                "Sorting strategy",
                options=list(SORTER_LIST.keys()),
                defaultValue=0,                       # Age-based is safest default
            )
        ) #:contentReference[oaicite:0]{index=0}

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Stratigraphic column",
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

        # 1 ► fetch user selections
        in_layer: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT_GEOLOGY, context)
        structure: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT_STRUCTURE, context)
        dtm: QgsRasterLayer = self.parameterAsRasterLayer(parameters, self.INPUT_DTM, context)
        contacts_layer: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.CONTACTS_LAYER, context)
        algo_index: int          = self.parameterAsEnum(parameters, self.SORTING_ALGORITHM, context)
        sorter_cls               = list(SORTER_LIST.values())[algo_index]

        feedback.pushInfo(f"Using sorter: {sorter_cls.__name__}")

        # 2 ► convert QGIS layers / tables to pandas
        # --------------------------------------------------
        # You must supply these three DataFrames:
        #   units_df           — required         (layerId, name, minAge, maxAge, group)
        #   relationships_df   — required         (Index1 / Unitname1, Index2 / Unitname2 …)
        #   contacts_df        — required for all but Age‐based
        #
        # Typical workflow:
        #   • iterate over in_layer.getFeatures()
        #   • build dicts/lists
        #   • pd.DataFrame(…)
        #
        # NB: map2loop does *not* need geometries – only attribute values.
        # --------------------------------------------------
        units_df= build_input_frames(in_layer, feedback,parameters)

        # 3 ► run the sorter
        sorter = sorter_cls()                     # instantiation is always zero-argument
        geology_gdf = qgsLayerToGeoDataFrame(in_layer)
        structure_gdf = qgsLayerToGeoDataFrame(structure)
        dtm_gdal = gdal.Open(dtm.source()) if dtm is not None and dtm.isValid() else None
        contacts_df = qgsLayerToGeoDataFrame(contacts_layer)
        relationships_df = contacts_df.copy()
        if 'length' in contacts_df.columns:
            relationships_df = relationships_df.drop(columns=['length'])
        if 'geometry' in contacts_df.columns:
            relationships_df = relationships_df.drop(columns=['geometry'])
        order = sorter.sort(
            units_df,
            relationships_df,
            contacts_df,
            geology_gdf,
            structure_gdf,
            dtm_gdal
        )

        # 4 ► write an in-memory table with the result
        sink_fields = QgsFields()
        sink_fields.append(QgsField("strat_pos", QMetaType.Type.Int))
        sink_fields.append(QgsField("unit_name", QMetaType.Type.QString))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            QgsWkbTypes.NoGeometry,
            in_layer.sourceCrs(),
        )

        for pos, name in enumerate(order, start=1):
            f = QgsFeature(sink_fields)
            f.setAttributes([pos, name])
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: dest_id}

    # ----------------------------------------------------------
    def createInstance(self) -> QgsProcessingAlgorithm:
        return StratigraphySorterAlgorithm()


# -------------------------------------------------------------------------
#  Helper stub – you must replace with *your* conversion logic
# -------------------------------------------------------------------------
def build_input_frames(layer: QgsVectorLayer, feedback, parameters) -> pd.DataFrame:
    """
    Placeholder that turns the geology layer (and any other project
    layers) into the four objects required by the sorter.

    Returns
    -------
    units_df
    """
    import pandas as pd
<<<<<<< HEAD

    unit_name_field = parameters.get('UNIT_NAME_FIELD', 'UNITNAME') if parameters else 'UNITNAME'
    min_age_field = parameters.get('MIN_AGE_FIELD', 'MIN_AGE') if parameters else 'MIN_AGE'
    max_age_field = parameters.get('MAX_AGE_FIELD', 'MAX_AGE') if parameters else 'MAX_AGE'
    group_field = parameters.get('GROUP_FIELD', 'GROUP') if parameters else 'GROUP'
=======
    from map2loop.map2loop.mapdata import MapData  # adjust import path if needed
>>>>>>> origin/processing/processing_tools_sampler

    # Example: convert the geology layer to a very small units_df
    units_records = []
    for f in layer.getFeatures():
        units_records.append(
            dict(
                layerId=f.id(),
                name=f[unit_name_field],           # attribute names → your schema
                minAge=float(f[min_age_field]),
                maxAge=float(f[max_age_field]),
                group=f[group_field],
            )
        )
    units_df = pd.DataFrame.from_records(units_records)

    # map_data can be mocked if you only use Age-based sorter

    feedback.pushInfo(f"Units → {len(units_df)} records")

    return units_df
