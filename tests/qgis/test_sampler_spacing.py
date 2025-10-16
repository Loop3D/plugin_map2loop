import unittest
from pathlib import Path
from qgis.core import QgsVectorLayer, QgsProcessingContext, QgsProcessingFeedback, QgsMessageLog, Qgis, QgsApplication
from qgis.testing import start_app
from loopstructural.processing.algorithms.sampler import SamplerAlgorithm
from loopstructural.processing.provider import Map2LoopProvider

class TestSamplerSpacing(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qgs = start_app()
        
        cls.provider = Map2LoopProvider()
        QgsApplication.processingRegistry().addProvider(cls.provider)

    def setUp(self):
        self.test_dir = Path(__file__).parent
        self.input_dir = self.test_dir / "input"
        
        self.geology_file = self.input_dir / "geol_clip_no_gaps.shp"
        
        self.assertTrue(self.geology_file.exists(), f"geology not found: {self.geology_file}")

    def test_spacing_50_with_geology(self):
        
        geology_layer = QgsVectorLayer(str(self.geology_file), "geology", "ogr")
        
        self.assertTrue(geology_layer.isValid(), "geology layer should be valid")
        self.assertGreater(geology_layer.featureCount(), 0, "geology layer should have features")
        
        QgsMessageLog.logMessage(f"geology layer: {geology_layer.featureCount()} features", "TestSampler", Qgis.Critical)
        QgsMessageLog.logMessage(f"spatial data-  geology layer", "TestSampler", Qgis.Critical)
        QgsMessageLog.logMessage(f"sampler type: Spacing", "TestSampler", Qgis.Critical)
        QgsMessageLog.logMessage(f"spacing: 50", "TestSampler", Qgis.Critical)
        
        algorithm = SamplerAlgorithm()
        algorithm.initAlgorithm()

        parameters = {
            'DTM': None,
            'GEOLOGY': None,
            'SPATIAL_DATA': geology_layer,
            'SAMPLER_TYPE': 1,
            'DECIMATION': 1,
            'SPACING': 50.0,
            'SAMPLED_CONTACTS': 'memory:sampled_points'
        }
        
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        try:
            QgsMessageLog.logMessage("Starting spacing sampler algorithm...", "TestSampler", Qgis.Critical)
            
            result = algorithm.processAlgorithm(parameters, context, feedback)
            
            QgsMessageLog.logMessage(f"Result: {result}", "TestSampler", Qgis.Critical)
            
            self.assertIsNotNone(result, "result should not be None")
            self.assertIn('SAMPLED_CONTACTS', result, "Result should contain SAMPLED_CONTACTS key")
            
            QgsMessageLog.logMessage("Spacing sampler test completed successfully!", "TestSampler", Qgis.Critical)
            
        except Exception as e:
            QgsMessageLog.logMessage(f"Spacing sampler test error: {str(e)}", "TestSampler", Qgis.Critical)
            QgsMessageLog.logMessage(f"Error type: {type(e).__name__}", "TestSampler", Qgis.Critical)
            import traceback
            QgsMessageLog.logMessage(f"Full traceback:\n{traceback.format_exc()}", "TestSampler", Qgis.Critical)
            raise
        
        finally:
            QgsMessageLog.logMessage("=" * 50, "TestSampler", Qgis.Critical)

    @classmethod
    def tearDownClass(cls):
        try:
            registry = QgsApplication.processingRegistry()
            registry.removeProvider(cls.provider)
        except Exception:
            pass

if __name__ == '__main__':
    unittest.main()
