#! python3

"""Main plugin module."""

# standard
from functools import partial
from pathlib import Path
from typing import Optional

# PyQGIS
from qgis.core import QgsApplication, QgsSettings
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator, QUrl, Qt
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QAction

# project
from m2l.__about__ import (
    DIR_PLUGIN_ROOT,
    __icon_path__,
    __title__,
    __uri_homepage__,
)
from m2l.gui.dlg_settings import PlgOptionsFactory
from m2l.gui.map2loop_dockwidget import Map2loopDockWidget
from m2l.processing import (
    Map2LoopProvider,
)
from m2l.toolbelt import PlgLogger

# ############################################################################
# ########## Classes ###############
# ##################################


class Map2LoopPlugin:
    def __init__(self, iface: QgisInterface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class which \
        provides the hook by which you can manipulate the QGIS application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.log = PlgLogger().log
        self.provider: Optional[Map2LoopProvider] = None
        self.dockwidget: Optional[Map2loopDockWidget] = None

        # translation
        # initialize the locale
        self.locale: str = QgsSettings().value("locale/userLocale", QLocale().name())[
            0:2
        ]
        locale_path: Path = (
            DIR_PLUGIN_ROOT
            / "resources"
            / "i18n"
            / f"{__title__.lower()}_{self.locale}.qm"
        )
        self.log(message=f"Translation: {self.locale}, {locale_path}", log_level=4)
        if locale_path.exists():
            self.translator = QTranslator()
            self.translator.load(str(locale_path.resolve()))
            QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        """Set up plugin UI elements."""

        # settings page within the QGIS preferences menu
        self.options_factory = PlgOptionsFactory()
        self.iface.registerOptionsWidgetFactory(self.options_factory)

        # -- Actions
        self.action_help = QAction(
            QgsApplication.getThemeIcon("mActionHelpContents.svg"),
            self.tr("Help"),
            self.iface.mainWindow(),
        )
        self.action_help.triggered.connect(
            partial(QDesktopServices.openUrl, QUrl(__uri_homepage__))
        )

        self.action_settings = QAction(
            QgsApplication.getThemeIcon("console/iconSettingsConsole.svg"),
            self.tr("Settings"),
            self.iface.mainWindow(),
        )
        self.action_settings.triggered.connect(
            lambda: self.iface.showOptionsDialog(
                currentPage="mOptionsPage{}".format(__title__)
            )
        )

        self.action_show_dockwidget = QAction(
            QIcon(str(__icon_path__)),
            self.tr("Map2Loop"),
            self.iface.mainWindow(),
        )
        self.action_show_dockwidget.setCheckable(True)
        self.action_show_dockwidget.triggered.connect(self.toggle_dockwidget)

        self.iface.addPluginToMenu(__title__, self.action_show_dockwidget)
        self.iface.addPluginToMenu(__title__, self.action_settings)
        self.iface.addPluginToMenu(__title__, self.action_help)
        
        self.iface.addToolBarIcon(self.action_show_dockwidget)
        # -- Processing
        self.initProcessing()

        # -- Help menu

        # documentation
        self.iface.pluginHelpMenu().addSeparator()
        self.action_help_plugin_menu_documentation = QAction(
            QIcon(str(__icon_path__)),
            f"{__title__} - Documentation",
            self.iface.mainWindow(),
        )
        self.action_help_plugin_menu_documentation.triggered.connect(
            partial(QDesktopServices.openUrl, QUrl(__uri_homepage__))
        )

        self.iface.pluginHelpMenu().addAction(
            self.action_help_plugin_menu_documentation
        )

    def initProcessing(self):
        """Initialize the processing provider."""
        self.provider = Map2LoopProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def init_dockwidget(self):
        if self.dockwidget is None:
            self.dockwidget = Map2loopDockWidget()
            self.dockwidget.closingPlugin.connect(self.on_dockwidget_closed)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)

    def toggle_dockwidget(self):
        if self.dockwidget is None:
            self.init_dockwidget()
        
        if self.dockwidget.isVisible():
            self.dockwidget.hide()
            self.action_show_dockwidget.setChecked(False)
        else:
            self.dockwidget.show()
            self.action_show_dockwidget.setChecked(True)

    def on_dockwidget_closed(self):
        self.action_show_dockwidget.setChecked(False)

    def tr(self, message: str) -> str:
        """Get the translation for a string using Qt translation API.

        :param message: string to be translated.
        :type message: str

        :returns: Translated version of message.
        :rtype: str
        """
        return QCoreApplication.translate(self.__class__.__name__, message)

    def unload(self):
        """Cleans up when plugin is disabled/uninstalled."""
        if self.dockwidget:
            self.iface.removeDockWidget(self.dockwidget)
            self.dockwidget = None
        
        self.iface.removeToolBarIcon(self.action_show_dockwidget)
        
        self.iface.removePluginMenu(__title__, self.action_show_dockwidget)
        self.iface.removePluginMenu(__title__, self.action_help)
        self.iface.removePluginMenu(__title__, self.action_settings)

        # -- Clean up preferences panel in QGIS settings
        self.iface.unregisterOptionsWidgetFactory(self.options_factory)
        # -- Unregister processing
        QgsApplication.processingRegistry().removeProvider(self.provider)

        # remove from QGIS help/extensions menu
        if self.action_help_plugin_menu_documentation:
            self.iface.pluginHelpMenu().removeAction(
                self.action_help_plugin_menu_documentation
            )

        # remove actions
        del self.action_show_dockwidget
        del self.action_settings
        del self.action_help

    def run(self):
        """Main process.

        :raises Exception: if there is no item in the feed
        """
        try:
            self.log(
                message=self.tr("Everything ran OK."),
                log_level=3,
                push=False,
            )
        except Exception as err:
            self.log(
                message=self.tr("Houston, we've got a problem: {}".format(err)),
                log_level=2,
                push=True,
            )
