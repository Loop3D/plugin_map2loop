from typing import Any, Optional

from qgis import processing
from qgis.core import (
    QgsFeatureSink,
    QgsFields, 
    QgsField, 
    QgsFeature, 
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterMatrix,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsSettings
)
from ...main.vectorLayerWrapper import qgsLayerToDataFrame
import json
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

# a lookup so we don’t need a giant if/else block
SORTER_LIST = {
    "Age‐based": SorterAgeBased,
    "NetworkX topological": SorterUseNetworkX,
    "Hint (deprecated)": SorterUseHint,
    "Adjacency α": SorterAlpha,
    "Maximise contacts": SorterMaximiseContacts,
    "Observation projections": SorterObservationProjections,
}

# class AutomaticStratigraphyAlgorithm(QgsProcessingAlgorithm):
#     """
#     Creates a one-column ‘stratigraphic column’ table ordered
#     by the selected map2loop sorter.
#     """
#     METHOD = "METHOD"
#     INPUT_GEOLOGY = "INPUT_GEOLOGY"
#     INPUT_STRATI_COLUMN = "INPUT_STRATI_COLUMN"
#     SORTING_ALGORITHM  = "SORTING_ALGORITHM"
#     OUTPUT = "OUTPUT"

#     # ----------------------------------------------------------
#     #  Metadata
#     # ----------------------------------------------------------
#     def name(self) -> str:
#         return "loop_sorter"

#     def displayName(self) -> str:
#         return "Stratigraphy Tools: Automatic Stratigraphic Column"

#     def group(self) -> str:
#         return "Stratigraphy Tools"

#     def groupId(self) -> str:
#         return "Loop3d"

#     # ----------------------------------------------------------
#     #  Parameters
#     # ----------------------------------------------------------
#     def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:

#         self.addParameter(
#             QgsProcessingParameterFeatureSource(
#                 self.INPUT_GEOLOGY,
#                 "Geology polygons",
#                 [QgsProcessing.TypeVectorPolygon],
#             )
#         )
        
#         strati_settings = QgsSettings()
#         last_strati_column = strati_settings.value("m2l/strati_column", "")
#         self.addParameter(
#             QgsProcessingParameterMatrix(
#                 name=self.INPUT_STRATI_COLUMN,
#                 description="Stratigraphic Order",
#                 headers=["Unit"],
#                 numberRows=0,
#                 defaultValue=last_strati_column
#             )
#         )

#         # enum so the user can pick the strategy from a dropdown
#         self.addParameter(
#             QgsProcessingParameterEnum(
#                 self.SORTING_ALGORITHM,
#                 "Sorting strategy",
#                 options=list(SORTER_LIST.keys()),
#                 defaultValue=0,                       # Age-based is safest default
#             )
#         ) #:contentReference[oaicite:0]{index=0}

#         self.addParameter(
#             QgsProcessingParameterFeatureSink(
#                 self.OUTPUT,
#                 "Stratigraphic column",
#             )
#         )

#     # ----------------------------------------------------------
#     #  Core
#     # ----------------------------------------------------------
#     def processAlgorithm(
#         self,
#         parameters: dict[str, Any],
#         context: QgsProcessingContext,
#         feedback: QgsProcessingFeedback,
#     ) -> dict[str, Any]:

#         # 1 ► fetch user selections
#         geology: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
#         algorithm_index: int          = self.parameterAsEnum(parameters, self.ALGO, context)
#         sorter_class               = list(SORTER_LIST.values())[algorithm_index]

#         feedback.pushInfo(f"Using sorter: {sorter_class.__name__}")

#         # 2 ► convert QGIS layers / tables to pandas
#         # geology = 

#         # 3 ► run the sorter
#         # sorter = sorter_cls()                     # instantiation is always zero-argument
#         # order  = sorter.sort(
#         #     units_df,
#         #     relationships_df,
#         #     contacts_df,
#         #     map_data,
#         # )

#         # 4 ► write an in-memory table with the result
#         sink_fields = QgsFields()
#         sink_fields.append(QgsField("strat_pos", int))
#         sink_fields.append(QgsField("unit_name", str))

#         (sink, dest_id) = self.parameterAsSink(
#             parameters,
#             self.OUTPUT,
#             context,
#             sink_fields,
#             QgsWkbTypes.NoGeometry,
#             geology.sourceCrs(),
#         )

#         for pos, name in enumerate(order, start=1):
#             f = QgsFeature(sink_fields)
#             f.setAttributes([pos, name])
#             sink.addFeature(f, QgsFeatureSink.FastInsert)

#         return {self.OUTPUT: dest_id}

#     # ----------------------------------------------------------
#     def createInstance(self) -> QgsProcessingAlgorithm:
#         return __class__()


class UserDefinedStratigraphyAlgorithm(QgsProcessingAlgorithm):
    """
    Creates a one-column ‘stratigraphic column’ table ordered
    by the selected map2loop sorter.
    """
    INPUT_STRATI_COLUMN = "INPUT_STRATI_COLUMN"
    OUTPUT = "OUTPUT"

    # ----------------------------------------------------------
    #  Metadata
    # ----------------------------------------------------------
    def name(self) -> str:
        return "loop_sorter"

    def displayName(self) -> str:
        return "Stratigraphy: User-Defined Stratigraphic Column"

    def group(self) -> str:
        return "Stratigraphy"

    def groupId(self) -> str:
        return "Stratigraphy_Column"

    # ----------------------------------------------------------
    #  Parameters
    # ----------------------------------------------------------
    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        
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
        
        strati_column = self.parameterAsMatrix(parameters, self.INPUT_STRATI_COLUMN, context)
        strati_settings = QgsSettings()
        last_strati_column = strati_settings.value("m2l/strati_column", "")

        json_list = json.dumps(strati_column)

        return {self.OUTPUT: json_list}

    # ----------------------------------------------------------
    def createInstance(self) -> QgsProcessingAlgorithm:
        return __class__()
