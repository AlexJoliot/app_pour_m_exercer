########################################################################
## QT GUI BY SPINN TV(YOUTUBE)
########################################################################

import os
import sys
import datetime

# Optimisation: Désactiver le scaling DPI automatique qui peut causer des lags
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "Ceil"

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt
from qt_material import *
########################################################################
# IMPORT GUI FILE
from src.ui_interface import *
########################################################################
from src.Functions import GuiFunctions
########################################################################
# IMPORT Custom widgets
from Custom_Widgets import *
from Custom_Widgets.QAppSettings import QAppSettings
from Custom_Widgets.QCustomQToolTip import QCustomQToolTipFilter
########################################################################
# IMPORT Login Dialog
from src.login_dialog import LoginDialog
########################################################################
# IMPORT Devices management
from src.devices_data import register_device, get_current_device_info
########################################################################
# IMPORT GT Token System
from src.gt_token_system import get_gt_system, mettre_a_jour_capacite
########################################################################

########################################################################
## MAIN WINDOW CLASS
########################################################################
class MainWindow(QMainWindow):
    def __init__(self, logged_in_user, parent=None):
        QMainWindow.__init__(self)
        self.logged_in_user = logged_in_user
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # Optimisation: Désactiver la translucidité qui peut causer des lags
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Use this to specify your json file(s) path/name
        loadJsonStyle(self, self.ui, jsonFiles = {
            "json-styles/style.json"
            }) 

        ########################################################################

        #######################################################################
        # SHOW WINDOW
        #######################################################################
        self.show() 

        # Optimisation: Supprimer la correction complexe des attributs de fenêtre
        # qui causait des problèmes de performance
        
        # Initialiser les fonctions GUI
        self.functions = GuiFunctions(self)
        
        # Charger les tournois terminés
        self.functions.load_finished_tournaments()
        
        # Appliquer les paramètres de l'application
        QAppSettings.updateAppSettings(self)
        
    def sassCompilationProgress(self,n):
        """n is the percentage"""
        self.ui.activityProgress.setValue(n)

########################################################################
## EXECUTE APP
########################################################################
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Optimisation: Désactiver les attributs qui causent des lags
    app.setAttribute(Qt.AA_UseOpenGLES, True)
    app.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app.setAttribute(Qt.AA_DisableHighDpiScaling, True)
    
    ########################################################################
    # Enregistrer l'appareil au démarrage de l'application
    ########################################################################
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Démarrage de l'application...")
    device_info, is_new_device = register_device()
    if is_new_device:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Nouvel appareil détecté!")
        print(f"  - hostname: {device_info.get('hostname')}")
        print(f"  - plateforme: {device_info.get('platform')}")
        print(f"  - CPU: {device_info.get('cpu')}")
        print(f"  - GPU: {device_info.get('gpu')}")
        print(f"  - TFLOPs: {device_info.get('tflops')}")
    else:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Appareil déjà enregistré")
    print(f"  - TFLOPs: {device_info.get('tflops')}")
    
    ########################################################################
    # Initialiser le système GT Token au démarrage
    ########################################################################
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Initialisation du système GT Token...")
    try:
        gt_system = get_gt_system()
        # Mettre à jour la capacité réseau au démarrage
        capacite = mettre_a_jour_capacite()
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Capacité réseau: {capacite['c_utilisable']:,.2f} TFLOP·h")
    except Exception as e:
        print(f"[ERREUR] Échec de l'initialisation GT: {e}")
    
    ########################################################################
    ##
    ########################################################################
    app_tooltip_filter = QCustomQToolTipFilter(tailPosition="auto")
    app.installEventFilter(app_tooltip_filter)

    login_dialog = LoginDialog()
    if login_dialog.exec() == QDialog.Accepted:
        logged_in_user = login_dialog.logged_in_user
        window = MainWindow(logged_in_user)
        # Load user profile after login
        window.functions.load_user_profile()
        window.show()
        sys.exit(app.exec_())
    else:
        sys.exit(0)
########################################################################
## END===>
########################################################################  
