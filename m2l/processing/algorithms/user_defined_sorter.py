from typing import Any, Optional
from osgeo import gdal
import numpy as np
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
    QgsCoordinateReferenceSystem,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsSettings
)


from qgis.core import (
    QgsFields, QgsField, QgsFeature, QgsFeatureSink, QgsWkbTypes,
    QgsCoordinateReferenceSystem, QgsProcessingAlgorithm, QgsProcessingContext,
    QgsProcessingFeedback, QgsProcessingParameterFeatureSink, QgsProcessingParameterMatrix,
    QgsSettings
)
from PyQt5.QtCore import QVariant
import numpy as np

class UserDefinedStratigraphyAlgorithm(QgsProcessingAlgorithm):
    INPUT_STRATI_COLUMN = "INPUT_STRATI_COLUMN"
    OUTPUT = "OUTPUT"

    def name(self): return "loop_sorter_2"
    def displayName(self): return "User-Defined Stratigraphic Column"
    def group(self): return "Stratigraphy"
    def groupId(self): return "Stratigraphy_Column"

    def initAlgorithm(self, config=None):
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

    def processAlgorithm(self, parameters, context, feedback):
        # 1) Read the matrix; it may be a list of lists (rows) or a flat list depending on input source.
        matrix = self.parameterAsMatrix(parameters, self.INPUT_STRATI_COLUMN, context)

        # Normalize to a list of unit strings (one column: "Unit")
        units = []
        for row in matrix:
            if isinstance(row, (list, tuple)):
                unit = row[0] if row else ""
            else:
                unit = row
            unit = (unit or "").strip()
            if unit:  # skip empty rows to avoid writing "" into fields
                units.append(unit)

        # 2) Build sequential order (1-based), cast to native int
        order_vals = [int(i) for i in (np.arange(len(units)) + 1)]

        # 3) Prepare sink
        sink_fields = QgsFields()
        sink_fields.append(QgsField("order", QVariant.Int))      # or QVariant.LongLong
        sink_fields.append(QgsField("unit_name", QVariant.String))

        crs = context.project().crs() if context and context.project() else QgsCoordinateReferenceSystem()
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            sink_fields, QgsWkbTypes.NoGeometry, crs
        )

        # 4) Insert features
        for pos, unit_name in zip(order_vals, units):
            f = QgsFeature(sink_fields)
            # Ensure correct types: int for "order", str for "unit_name"
            f.setAttributes([int(pos), str(unit_name)])
            ok = sink.addFeature(f, QgsFeatureSink.FastInsert)
            if not ok:
                feedback.reportError(f"Failed to add feature for unit '{unit_name}' (order={pos}).")

        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return __class__()
