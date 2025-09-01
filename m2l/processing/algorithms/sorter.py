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

    INPUT = "INPUT"
    ALGO  = "SORT_ALGO"
    OUTPUT = "OUTPUT"

    # ----------------------------------------------------------
    #  Metadata
    # ----------------------------------------------------------
    def name(self) -> str:
        return "loop_sorter"

    def displayName(self) -> str:
        return "loop: Stratigraphic sorter"

    def group(self) -> str:
        return "Loop3d"

    def groupId(self) -> str:
        return "loop3d"

    # ----------------------------------------------------------
    #  Parameters
    # ----------------------------------------------------------
    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                "Geology polygons",
                [QgsProcessing.TypeVectorPolygon],
            )
        )

        # enum so the user can pick the strategy from a dropdown
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ALGO,
                "Sorting strategy",
                options=list(SORTER_LIST.keys()),
                defaultValue=0,                       # Age-based is safest default
            )
        ) #:contentReference[oaicite:0]{index=0}

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr("Stratigraphic column"),
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
        in_layer: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        algo_index: int          = self.parameterAsEnum(parameters, self.ALGO, context)
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
        units_df, relationships_df, contacts_df, map_data = build_input_frames(in_layer, feedback)

        # 3 ► run the sorter
        sorter = sorter_cls()                     # instantiation is always zero-argument
        order  = sorter.sort(
            units_df,
            relationships_df,
            contacts_df,
            map_data,
        )

        # 4 ► write an in-memory table with the result
        sink_fields = QgsFields()
        sink_fields.append(QgsField("strat_pos", int))
        sink_fields.append(QgsField("unit_name", str))

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
def build_input_frames(layer: QgsVectorLayer, feedback) -> tuple:
    """
    Placeholder that turns the geology layer (and any other project
    layers) into the four objects required by the sorter.

    Returns
    -------
    (units_df, relationships_df, contacts_df, map_data)
    """
    import pandas as pd
    from m2l.map2loop.mapdata import MapData  # adjust import path if needed

    # Example: convert the geology layer to a very small units_df
    units_records = []
    for f in layer.getFeatures():
        units_records.append(
            dict(
                layerId=f.id(),
                name=f["UNITNAME"],           # attribute names → your schema
                minAge=f.attribute("MIN_AGE"),
                maxAge=f.attribute("MAX_AGE"),
                group=f["GROUP"],
            )
        )
    units_df = pd.DataFrame.from_records(units_records)

    # relationships_df and contacts_df are domain-specific ─ fill them here
    relationships_df = pd.DataFrame(columns=["Index1", "UNITNAME_1", "Index2", "UNITNAME_2"])
    contacts_df      = pd.DataFrame(columns=["UNITNAME_1", "UNITNAME_2", "length"])

    # map_data can be mocked if you only use Age-based sorter
    map_data = MapData()   # or MapData.from_project(…) / MapData.from_files(…)

    feedback.pushInfo(f"Units → {len(units_df)} records")

    return units_df, relationships_df, contacts_df, map_data
