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

from typing import Any, Optional

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


class BasalContactsAlgorithm(QgsProcessingAlgorithm):
    """Processing algorithm to create basal contacts."""

    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        """Return the algorithm name."""
        return "loop: basal_contacts"

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
                self.INPUT,
                "Geology Polygons",
                [QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Basal Contacts",
            )
        )
        pass

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        pass

    def createInstance(self) -> QgsProcessingAlgorithm:
        """Create a new instance of the algorithm."""
        return self.__class__()  # BasalContactsAlgorithm()
