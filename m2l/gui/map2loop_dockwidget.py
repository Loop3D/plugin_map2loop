"""
 map2loop plugin Docker Widget
"""

import os
import geopandas

from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox
from qgis.core import (
    QgsMapLayerProxyModel, 
    QgsVectorLayer, 
    QgsProject, 
    QgsFeature, 
    QgsGeometry,
    QgsFields,
    QgsField,
    QgsWkbTypes
)

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'map2loop_dockwidget_base.ui'))


class Map2loopDockWidget(QDockWidget, FORM_CLASS):
    
    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(Map2loopDockWidget, self).__init__(parent)
        
        self.setupUi(self)
        self.setWindowTitle("map2loop")
        self.setup_qgis_widgets()
        
        self.extract_contact_button.clicked.connect(self.extract_contact)
        self.extract_basal_contact_button.clicked.connect(self.extract_basal_contact)
        
    
    def setup_qgis_widgets(self):
        input_data_formLayout = self.input_data_groupBox.findChild(QtWidgets.QFormLayout, 'input_data_formLayout')
        
        self.geology_layer = QgsMapLayerComboBox()
        self.geology_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        input_data_formLayout.replaceWidget(self.geology_comboBox, self.geology_layer)
        self.geology_comboBox.hide()
        
        self.structure_layer = QgsMapLayerComboBox()
        self.structure_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        input_data_formLayout.replaceWidget(self.structure_comboBox, self.structure_layer)
        self.structure_comboBox.hide()

        self.dtm_layer = QgsMapLayerComboBox()
        self.dtm_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        input_data_formLayout.replaceWidget(self.dtm_comboBox, self.dtm_layer)
        self.dtm_comboBox.hide()

        self.fault_layer = QgsMapLayerComboBox()
        self.fault_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        input_data_formLayout.replaceWidget(self.fault_comboBox, self.fault_layer)
        self.fault_comboBox.hide()

        self.strat_column_layer = QgsMapLayerComboBox()
        self.strat_column_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        input_data_formLayout.replaceWidget(self.strat_column_comboBox, self.strat_column_layer)
        self.strat_column_comboBox.hide()

        self.unit_name_field = QgsFieldComboBox()
        input_data_formLayout.replaceWidget(self.unit_name_field_comboBox, self.unit_name_field)
        self.unit_name_field_comboBox.hide()
        
        self.geology_layer.layerChanged.connect(self.update_unit_name_field)

    def update_unit_name_field(self):
        geology_layer = self.geology_layer.currentLayer()
        self.unit_name_field.setLayer(geology_layer)
        if geology_layer:
            fields = geology_layer.fields()
            for field in fields:
                if field.name().lower() in ['unitname', 'unit_name']:
                    self.unit_name_field.setField(field.name())
                    break
    
    def get_strat_column_source(self, context, feedback=None):
        from qgis.core import QgsProcessingUtils
        
        layer = self.strat_column_layer.currentLayer()
        if layer:
            layer_string = layer.id()
            source = QgsProcessingUtils.mapLayerFromString(layer_string, context)
            return source
        return None

    def extract_contact(self):
        geology_layer = self.geology_layer.currentLayer()
        fault_layer = self.fault_layer.currentLayer()
        
        if not geology_layer:
            QtWidgets.QMessageBox.warning(self,"No Geology Layer Selected","Please select a geology layer")
            return
        
        try:
            geology_gdf = geopandas.read_file(geology_layer.source())
            fault_gdf = geopandas.read_file(fault_layer.source()) if fault_layer else None
            
            unit_name_field = self.unit_name_field.currentField()
            
            if unit_name_field and unit_name_field != 'UNITNAME' and unit_name_field in geology_gdf.columns:
                geology_gdf = geology_gdf.rename(columns={unit_name_field: 'UNITNAME'})
            elif 'UNITNAME' not in geology_gdf.columns:
                QtWidgets.QMessageBox.warning(self,"Missing Unit Name Field","Please select a unit name field from the geology layer.")
                return
            
            try:
                from m2l.processing.algorithms.extract_contacts import ContactExtractor
                contact_extractor = ContactExtractor(geology_gdf, fault_gdf)
                contacts = contact_extractor.extract_all_contacts()
                
                if contacts is not None and len(contacts) > 0:
                    contacts_layer = self.create_vector_layer_from_geodataframe(contacts, "Extracted_Contacts")
                    if contacts_layer:
                        QgsProject.instance().addMapLayer(contacts_layer)
                        
                        QtWidgets.QMessageBox.information(self,"Contact Extraction Complete",f"Extracted {len(contacts)} contacts and exported as '{contacts_layer.name()}'")
                    else:
                        QtWidgets.QMessageBox.warning(self,"Layer Creation Failed","Failed to create vector layer from contacts")
                else:
                    QtWidgets.QMessageBox.information(self,"No Contacts Found","No contacts were extracted")
                    
            except ImportError:
                QtWidgets.QMessageBox.warning(self,"ContactExtractor Not Found","ContactExtractor class not found.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self,"Error",f"An error occurred during contact extraction: {str(e)}")

    def extract_basal_contact(self):
        geology_layer = self.geology_layer.currentLayer()
        fault_layer = self.fault_layer.currentLayer()
        strat_column_layer = self.strat_column_layer.currentLayer()
        
        if not geology_layer:
            QtWidgets.QMessageBox.warning(self,"No Geology Layer Selected","Please select a geology layer")
            return
            
        if not strat_column_layer:
            QtWidgets.QMessageBox.warning(self,"No Stratigraphic Column Selected","Please select a stratigraphic column layer")
            return
        
        try:
            geology_gdf = geopandas.read_file(geology_layer.source())
            fault_gdf = geopandas.read_file(fault_layer.source()) if fault_layer else None
            
            unit_name_field = self.unit_name_field.currentField()
            
            if unit_name_field and unit_name_field != 'UNITNAME' and unit_name_field in geology_gdf.columns:
                geology_gdf = geology_gdf.rename(columns={unit_name_field: 'UNITNAME'})
            elif 'UNITNAME' not in geology_gdf.columns:
                QtWidgets.QMessageBox.warning(self,"Missing Unit Name Field","Please select a unit name field from the geology layer, or ensure the geology layer has a 'UNITNAME' column.")
                return
            
            stratigraphic_column = self.get_stratigraphic_column_list(strat_column_layer)
            if not stratigraphic_column:
                QtWidgets.QMessageBox.warning(self,"Empty Stratigraphic Column","The stratigraphic column layer contains no valid unit names.")
                return
            
            try:
                from m2l.processing.algorithms.extract_contacts import ContactExtractor
                contact_extractor = ContactExtractor(geology_gdf, fault_gdf)
                basal_contacts = contact_extractor.extract_basal_contacts(stratigraphic_column)
                
                if basal_contacts is not None and len(basal_contacts) > 0:
                    basal_contacts_layer = self.create_vector_layer_from_geodataframe(basal_contacts, "Extracted_Basal_Contacts")
                    if basal_contacts_layer:
                        QgsProject.instance().addMapLayer(basal_contacts_layer)
                        
                        QtWidgets.QMessageBox.information(self, "Basal Contact Extraction Complete",f"Extracted {len(basal_contacts)} basal contacts and exported as '{basal_contacts_layer.name()}'")
                    else:
                        QtWidgets.QMessageBox.warning(self,"Layer Creation Failed","Failed to create vector layer from basal contacts")
                else:
                    QtWidgets.QMessageBox.information(self,"No Basal Contacts Found","No basal contacts were extracted")
                    
            except ImportError:
                QtWidgets.QMessageBox.warning(self,"ContactExtractor Not Found","ContactExtractor class not found.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self,"Error",f"An error occurred during basal contact extraction: {str(e)}")

    def get_stratigraphic_column_list(self, strat_layer):
        try:
            field_names = [field.name() for field in strat_layer.fields()]
            unit_field = None
            
            for field_name in field_names:
                if field_name.lower() in ['unit_name', 'unitname', 'unit', 'formation', 'name']:
                    unit_field = field_name
                    break
            
            if not unit_field and field_names:
                unit_field = field_names[0]
            
            if not unit_field:
                return []
            
            unit_names = []
            for feature in strat_layer.getFeatures():
                unit_name = feature[unit_field]
                if unit_name and str(unit_name).strip():
                    unit_names.append(str(unit_name).strip())
            
            seen = set()
            stratigraphic_column = []
            for unit in unit_names:
                if unit not in seen:
                    seen.add(unit)
                    stratigraphic_column.append(unit)
            
            return stratigraphic_column
            
        except Exception as e:
            print(f"Error extracting stratigraphic column: {str(e)}")
            return []

    def create_vector_layer_from_geodataframe(self, geodataframe, layer_name="Vector_Layer"):
        try:
            if hasattr(geodataframe, 'geometry') and len(geodataframe) > 0:
                first_geom = geodataframe.geometry.iloc[0]
                if first_geom.geom_type == 'LineString':
                    geom_type = "LineString"
                elif first_geom.geom_type == 'Point':
                    geom_type = "Point"
                elif first_geom.geom_type == 'Polygon':
                    geom_type = "Polygon"
                else:
                    geom_type = "LineString"
                if not geodataframe.crs:
                    QtWidgets.QMessageBox.warning(self,"No CRS Found","No CRS found in the geodataframe.")
                    return None
                crs_string = f"EPSG:{geodataframe.crs.to_epsg()}"
            else:
                geom_type = "LineString"
            
            layer = QgsVectorLayer(f"{geom_type}?crs={crs_string}", layer_name, "memory")
            
            if not layer.isValid():
                return None
            
            provider = layer.dataProvider()
            
            fields = QgsFields()
            if hasattr(geodataframe, 'columns'):
                for col in geodataframe.columns:
                    if col != 'geometry':
                        if geodataframe[col].dtype == 'object':
                            fields.append(QgsField(col, QVariant.String))
                        elif geodataframe[col].dtype in ['int8', 'int16', 'int32', 'int64']:
                            fields.append(QgsField(col, QVariant.Int))
                        elif geodataframe[col].dtype in ['float16', 'float32', 'float64']:
                            fields.append(QgsField(col, QVariant.Double))
                        else:
                            fields.append(QgsField(col, QVariant.String))
            else:
                fields.append(QgsField("feature_id", QVariant.Int))
                fields.append(QgsField("feature_type", QVariant.String))
            
            provider.addAttributes(fields)
            layer.updateFields()
            
            features = []
            if hasattr(geodataframe, 'iterrows'):
                for _idx, row in geodataframe.iterrows():
                    feature = QgsFeature()
                    
                    if hasattr(row, 'geometry') and row.geometry is not None:
                        geom = QgsGeometry.fromWkt(row.geometry.wkt)
                        feature.setGeometry(geom)
                    
                    attributes = []
                    for col in geodataframe.columns:
                        if col != 'geometry':
                            attributes.append(row[col])
                    feature.setAttributes(attributes)
                    features.append(feature)
            else:
                for i, _item in enumerate(geodataframe):
                    feature = QgsFeature()
                    feature.setAttributes([i, "feature"])
                    features.append(feature)
            
            provider.addFeatures(features)
            layer.updateExtents()
            
            return layer
            
        except Exception as e:
            print(f"Error creating vector layer from geodataframe: {str(e)}")
            return None
    
    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()