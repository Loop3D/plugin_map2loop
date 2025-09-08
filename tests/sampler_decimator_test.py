"""
qgis python console:
   ```
   import sys
   dir = your_directory_to_the_plugin_code
   sys.path.append(dir)
   import unittest
   from tests.sampler_decimator_test import TestSamplerDecimator
   suite = unittest.TestLoader().loadTestsFromTestCase(TestSamplerDecimator)
   unittest.TextTestRunner(verbosity=2).run(suite)
   ```
"""

import unittest
from pathlib import Path
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsProcessingContext, QgsProcessingFeedback, QgsMessageLog, Qgis
from m2l.processing.algorithms.sampler import SamplerAlgorithm

class TestSamplerDecimator(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(__file__).parent
        self.input_dir = self.test_dir / "input"
        
        self.geology_file = self.input_dir / "geol_clip_no_gaps.shp"
        self.structure_file = self.input_dir / "structure_clip.shp"
        self.dtm_file = self.input_dir / "dtm_rp.tif"
        
        self.assertTrue(self.geology_file.exists(), f"geology not found: {self.geology_file}")
        self.assertTrue(self.structure_file.exists(), f"structure not found: {self.structure_file}")
        self.assertTrue(self.dtm_file.exists(), f"dtm not found: {self.dtm_file}")

    def test_decimator_1_with_structure(self):
        
        geology_layer = QgsVectorLayer(str(self.geology_file), "geology", "ogr")
        structure_layer = QgsVectorLayer(str(self.structure_file), "structure", "ogr")
        dtm_layer = QgsRasterLayer(str(self.dtm_file), "dtm")
        
        self.assertTrue(geology_layer.isValid(), "geology layer should be valid")
        self.assertTrue(structure_layer.isValid(), "structure layer should be valid")
        self.assertTrue(dtm_layer.isValid(), "dtm layer should be valid")
        self.assertGreater(geology_layer.featureCount(), 0, "geology layer should have features")
        self.assertGreater(structure_layer.featureCount(), 0, "structure layer should have features")
        
        QgsMessageLog.logMessage(f"geology layer valid: {geology_layer.isValid()}", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"structure layer valid: {structure_layer.isValid()}", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"dtm layer valid: {dtm_layer.isValid()}", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"dtm source: {dtm_layer.source()}", "TestDecimator", Qgis.Critical)
        
        QgsMessageLog.logMessage(f"geology layer: {geology_layer.featureCount()} features", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"structure layer: {structure_layer.featureCount()} features", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"spatial data- structure layer", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"sampler type: Decimator", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"decimation: 1", "TestDecimator", Qgis.Critical)
        QgsMessageLog.logMessage(f"dtm: {self.dtm_file.name}", "TestDecimator", Qgis.Critical)
        
        algorithm = SamplerAlgorithm()
        algorithm.initAlgorithm()

        parameters = {
            'DTM': dtm_layer,
            'GEOLOGY': geology_layer,
            'SPATIAL_DATA': structure_layer,
            'SAMPLER_TYPE': 0,
            'DECIMATION': 1,
            'SPACING': 200.0,
            'SAMPLED_CONTACTS': 'memory:decimated_points'
        }
        
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()
        
        
        try:
            QgsMessageLog.logMessage("Starting decimator sampler algorithm...", "TestDecimator", Qgis.Critical)
            
            result = algorithm.processAlgorithm(parameters, context, feedback)
            
            QgsMessageLog.logMessage(f"Result: {result}", "TestDecimator", Qgis.Critical)
            
            self.assertIsNotNone(result, "result should not be None")
            self.assertIn('SAMPLED_CONTACTS', result, "Result should contain SAMPLED_CONTACTS key")
            
            QgsMessageLog.logMessage("Decimator sampler test completed successfully!", "TestDecimator", Qgis.Critical)
            
        except Exception as e:
            QgsMessageLog.logMessage(f"Decimator sampler test error: {str(e)}", "TestDecimator", Qgis.Critical)
            QgsMessageLog.logMessage(f"Error type: {type(e).__name__}", "TestDecimator", Qgis.Critical)

            import traceback
            QgsMessageLog.logMessage(f"Full traceback:\n{traceback.format_exc()}", "TestDecimator", Qgis.Critical)
            raise
        
        finally:
            QgsMessageLog.logMessage("=" * 50, "TestDecimator", Qgis.Critical)

if __name__ == '__main__':
    unittest.main()
