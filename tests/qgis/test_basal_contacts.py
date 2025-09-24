import unittest
from pathlib import Path
from qgis.core import QgsVectorLayer, QgsProcessingContext, QgsProcessingFeedback, QgsMessageLog, Qgis, QgsApplication
from qgis.testing import start_app
from m2l.processing.algorithms.extract_basal_contacts import BasalContactsAlgorithm
from m2l.processing.provider import Map2LoopProvider

class TestBasalContacts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qgs = start_app()
        
        cls.provider = Map2LoopProvider()
        QgsApplication.processingRegistry().addProvider(cls.provider)

    def setUp(self):
        self.test_dir = Path(__file__).parent
        self.input_dir = self.test_dir / "input"
        
        self.geology_file = self.input_dir / "geol_clip_no_gaps.shp"
        self.faults_file = self.input_dir / "faults_clip.shp"
        
        self.assertTrue(self.geology_file.exists(), f"geology not found: {self.geology_file}")

        if not self.faults_file.exists():
            QgsMessageLog.logMessage(f"faults not found: {self.faults_file}, will run test without faults", "TestBasalContacts", Qgis.Warning)

    def test_basal_contacts_extraction(self):
        
        geology_layer = QgsVectorLayer(str(self.geology_file), "geology", "ogr")
        
        self.assertTrue(geology_layer.isValid(), "geology layer should be valid")
        self.assertGreater(geology_layer.featureCount(), 0, "geology layer should have features")
        
        faults_layer = None
        if self.faults_file.exists():
            faults_layer = QgsVectorLayer(str(self.faults_file), "faults", "ogr")
            self.assertTrue(faults_layer.isValid(), "faults layer should be valid")
            self.assertGreater(faults_layer.featureCount(), 0, "faults layer should have features")
            QgsMessageLog.logMessage(f"faults layer: {faults_layer.featureCount()} features", "TestBasalContacts", Qgis.Critical)
        
        QgsMessageLog.logMessage(f"geology layer: {geology_layer.featureCount()} features", "TestBasalContacts", Qgis.Critical)
        
        strati_column = [
            "Turee Creek Group",
            "Boolgeeda Iron Formation",
            "Woongarra Rhyolite",
            "Weeli Wolli Formation",
            "Brockman Iron Formation",
            "Mount McRae Shale and Mount Sylvia Formation",
            "Wittenoom Formation",
            "Marra Mamba Iron Formation",
            "Jeerinah Formation",
            "Bunjinah Formation",
            "Pyradie Formation",
            "Fortescue Group",
            "Hardey Formation",
            "Boongal Formation",
            "Mount Roe Basalt",
            "Rocklea Inlier greenstones",
            "Rocklea Inlier metagranitic unit"
        ]

        algorithm = BasalContactsAlgorithm()
        algorithm.initAlgorithm()

        parameters = {
            'GEOLOGY': geology_layer,
            'UNIT_NAME_FIELD': 'unitname',
            'FORMATION_FIELD': 'formation',
            'FAULTS': faults_layer,
            'STRATIGRAPHIC_COLUMN': strati_column,
            'IGNORE_UNITS': [],
            'BASAL_CONTACTS': 'memory:basal_contacts',
            'ALL_CONTACTS': 'memory:all_contacts'
        }
        
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        try:
            QgsMessageLog.logMessage("Starting basal contacts algorithm...", "TestBasalContacts", Qgis.Critical)
            
            result = algorithm.processAlgorithm(parameters, context, feedback)
            
            QgsMessageLog.logMessage(f"Result: {result}", "TestBasalContacts", Qgis.Critical)
            
            self.assertIsNotNone(result, "result should not be None")
            self.assertIn('BASAL_CONTACTS', result, "Result should contain BASAL_CONTACTS key")
            self.assertIn('ALL_CONTACTS', result, "Result should contain ALL_CONTACTS key")
            
            basal_contacts_layer = context.takeResultLayer(result['BASAL_CONTACTS'])
            self.assertIsNotNone(basal_contacts_layer, "basal contacts layer should not be None")
            self.assertTrue(basal_contacts_layer.isValid(), "basal contacts layer should be valid")
            self.assertGreater(basal_contacts_layer.featureCount(), 0, "basal contacts layer should have features")
            
            QgsMessageLog.logMessage(f"Generated {basal_contacts_layer.featureCount()} basal contacts", 
                                     "TestBasalContacts", Qgis.Critical)
            
            all_contacts_layer = context.takeResultLayer(result['ALL_CONTACTS'])
            self.assertIsNotNone(all_contacts_layer, "all contacts layer should not be None")
            self.assertTrue(all_contacts_layer.isValid(), "all contacts layer should be valid")
            self.assertGreater(all_contacts_layer.featureCount(), 0, "all contacts layer should have features")

            QgsMessageLog.logMessage(f"Generated {all_contacts_layer.featureCount()} total contacts", 
                                    "TestBasalContacts", Qgis.Critical)
            
            QgsMessageLog.logMessage("Basal contacts test completed successfully!", "TestBasalContacts", Qgis.Critical)
            
        except Exception as e:
            QgsMessageLog.logMessage(f"Basal contacts test error: {str(e)}", "TestBasalContacts", Qgis.Critical)
            QgsMessageLog.logMessage(f"Error type: {type(e).__name__}", "TestBasalContacts", Qgis.Critical)
            import traceback
            QgsMessageLog.logMessage(f"Full traceback:\n{traceback.format_exc()}", "TestBasalContacts", Qgis.Critical)
            raise
        
        finally:
            QgsMessageLog.logMessage("=" * 50, "TestBasalContacts", Qgis.Critical)

    @classmethod
    def tearDownClass(cls):
        try:
            registry = QgsApplication.processingRegistry()
            registry.removeProvider(cls.provider)
        except Exception:
            pass

if __name__ == '__main__':
    unittest.main()