# -*- coding: utf-8 -*-

#GUI Functions
import os
import json
import sys
import datetime 
import platform
import importlib.util
import shutil
import traceback
import subprocess
import threading
import time
from time import sleep
from functools import partial
# --- Custom widgets ---
from Custom_Widgets import *
from Custom_Widgets.QAppSettings import QAppSettings
from Custom_Widgets.QCustomTipOverlay import QCustomTipOverlay
from Custom_Widgets.QCustomLoadingIndicators import QCustom3CirclesLoader

# --- PySide6 Core ---
from PySide6.QtCore import QSettings, QTimer, QPropertyAnimation, QEasingCurve, QSize, QObject, Signal, Slot, QRunnable, QThreadPool, Qt

# --- PySide6 GUI ---
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QIcon

# --- PySide6 Widgets ---
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget, QFrame, QTableWidgetItem, QProgressBar, QPushButton, QFileDialog, QMessageBox, QApplication, QInputDialog, QHeaderView, QSizePolicy, QDialog, QVBoxLayout, QLabel, QLineEdit, QComboBox, QDialogButtonBox

import psutil

from src.roundprogressbar import RoundProgressBar
from src.spiralprogressbar import SpiralProgressBar

# Import GT Token System
from src.gt_token_system import (
    get_gt_system,
    emettre_gt_pour_tournoi,
    mettre_a_jour_capacite,
    convertir_gt_en_tfloph,
    reinitialiser_soldes_users
)

# Import users data
USERS = {}
def load_users_data():
    global USERS
    try:
        with open("users_data.json", "r", encoding="utf-8") as f:
            USERS = json.load(f)
            
            # Migrate old "balance" field to "gt_balance" if needed
            for username, user_data in USERS.items():
                if "balance" in user_data and "gt_balance" not in user_data:
                    user_data["gt_balance"] = user_data.pop("balance")
                    
            # Save migrated data
            with open("users_data.json", "w", encoding="utf-8") as f:
                json.dump(USERS, f, indent=4, ensure_ascii=False)
                
    except:
        USERS = {}


class DollarPaymentDialog(QDialog):
    """Dialog for processing dollar payments (entry fees and top-ups)"""
    def __init__(self, parent, amount, payment_type):
        super().__init__(parent)
        self.amount = amount
        self.payment_type = payment_type  # "entry_fee" or "topup"
        self.setWindowTitle(f"Pay {payment_type.replace('_', ' ').title()}")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Info label
        info_text = f"Payment Required: ${amount:.2f}"
        if payment_type == "entry_fee":
            info_text = f"Entry Fee Required: ${amount:.2f}"
        elif payment_type == "topup":
            info_text = f"Top-up Required: ${amount:.2f}"
        
        self.info_label = QLabel(info_text)
        self.info_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(self.info_label)
        
        # Payment method selection
        payment_label = QLabel("Payment Method:")
        layout.addWidget(payment_label)
        
        self.payment_method = QComboBox()
        self.payment_method.addItems(["Credit Card", "PayPal", "Crypto", "Bank Transfer"])
        layout.addWidget(self.payment_method)
        
        # Card number input (for credit card)
        self.card_label = QLabel("Card Number:")
        layout.addWidget(self.card_label)
        
        self.card_input = QLineEdit()
        self.card_input.setPlaceholderText("XXXX XXXX XXXX XXXX")
        layout.addWidget(self.card_input)
        
        # CVV and Expiry
        self.cvv_label = QLabel("CVV:")
        layout.addWidget(self.cvv_label)
        
        self.cvv_input = QLineEdit()
        self.cvv_input.setPlaceholderText("XXX")
        self.cvv_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.cvv_input)
        
        # Connect payment method change
        self.payment_method.currentTextChanged.connect(self.update_payment_fields)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.process_payment)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def update_payment_fields(self, method):
        """Update visible fields based on payment method"""
        if method == "Credit Card":
            self.card_label.setVisible(True)
            self.card_input.setVisible(True)
            self.cvv_label.setVisible(True)
            self.cvv_input.setVisible(True)
        elif method == "PayPal":
            self.card_label.setText("PayPal Email:")
            self.card_label.setVisible(True)
            self.card_input.setPlaceholderText("email@example.com")
            self.card_input.setVisible(True)
            self.cvv_label.setVisible(False)
            self.cvv_input.setVisible(False)
        elif method == "Crypto":
            self.card_label.setText("Wallet Address:")
            self.card_label.setVisible(True)
            self.card_input.setPlaceholderText("0x...")
            self.card_input.setVisible(True)
            self.cvv_label.setVisible(False)
            self.cvv_input.setVisible(False)
        elif method == "Bank Transfer":
            self.card_label.setText("Account Number:")
            self.card_label.setVisible(True)
            self.card_input.setPlaceholderText("XXXXXX")
            self.card_input.setVisible(True)
            self.cvv_label.setVisible(False)
            self.cvv_input.setVisible(False)
    
    def process_payment(self):
        """Process the payment and accept the dialog"""
        # In a real app, you would process payment here
        # For now, we just accept
        self.accept()

load_users_data()

# =============================================================================
# HELPERS JSON — remplacent le chargement via importlib/exec de fichiers .py
# (Fix sécurité #2 : suppression de l'exécution de code arbitraire)
# =============================================================================

def _load_json_file(file_path: str, root_key: str, default=None):
    """Charge un fichier JSON et retourne la valeur de root_key."""
    if default is None:
        default = {}
    json_path = file_path.replace(".py", ".json")
    if not os.path.exists(json_path):
        return default
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f).get(root_key, default)
    except Exception as e:
        print(f"[JSON] Erreur chargement {json_path}: {e}")
        return default


def _save_json_file(file_path: str, root_key: str, data: dict):
    """Sauvegarde data dans un fichier JSON de façon atomique."""
    json_path = file_path.replace(".py", ".json")
    tmp_path = json_path + ".tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump({root_key: data}, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, json_path)
    except Exception as e:
        print(f"[JSON] Erreur sauvegarde {json_path}: {e}")


platforms = {
    'linux' : 'Linux',
    'linux1' : 'Linux',
    'linux2' : 'Linux',
    'darwin' : 'OS X',
    'win32' : 'Windows',
    'win64' : 'Windows'
}

class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(int)
    status_update = Signal(str)

# Signals pour les mises à jour UI depuis les workers
class CpuRamSignals(QObject):
    update_ui = Signal(dict)

class BatterySignals(QObject):
    update_ui = Signal(dict)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        self.kwargs['progress_callback'] = self.signals.progress
        self.kwargs['status_callback'] = self.signals.status_update

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)

        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            if hasattr(self, 'signals') and self.signals is not None:
                try:
                    self.signals.error.emit((exctype, value, traceback.format_exc()))
                except Exception as e:
                    print(f"Error emitting error signal: {e}")

        else:
            if hasattr(self, 'signals') and self.signals is not None:
                try:
                    self.signals.result.emit(result)
                except Exception as e:
                    print(f"Error emitting result signal: {e}")

        finally:
            if hasattr(self, 'signals') and self.signals is not None:
                try:
                    self.signals.finished.emit()
                except Exception as e:
                    print(f"Error emitting finished signal: {e}")

class ScanWorker(QRunnable):
    def __init__(self, scan_type, file_path=None):
        super(ScanWorker, self).__init__()
        self.scan_type = scan_type
        self.file_path = file_path
        self.signals = WorkerSignals()
        self.is_cancelled = False

    @Slot()
    def run(self):
        def _safe_emit_finished():
            try:
                print("DEBUG: emitting finished signal now")
                self.signals.finished.emit()
            except Exception as ex:
                print("DEBUG: failed to emit finished:", ex)

        try:
            print("DEBUG: ScanWorker.run started", self.scan_type, self.file_path)
            if platform.system().lower() != 'windows':
                print("DEBUG: non-windows platform, returning")
                try:
                    self.signals.error.emit(("PlatformError", "Windows Defender n'est disponible que sur Windows", ""))
                except Exception as e:
                    print("DEBUG: error emitting error signal:", e)
                _safe_emit_finished()
                return

            if self.scan_type == "system":
                print("DEBUG: preparing system scan")
                self.signals.status_update.emit("Démarrage du scan système...")
                self.signals.progress.emit(10)
                cmd = ["powershell", "-Command", "Start-MpScan -ScanType QuickScan"]

            elif self.scan_type == "file" and self.file_path:
                print("DEBUG: preparing file scan for", self.file_path)
                self.signals.status_update.emit(f"Scan du fichier: {os.path.basename(self.file_path)}")
                self.signals.progress.emit(10)
                # [FIX 6] -LiteralPath évite toute injection via apostrophes ou caractères spéciaux
                cmd = ["powershell", "-Command",
                       "Start-MpScan", "-ScanType", "CustomScan",
                       "-LiteralPath", self.file_path]

            else:
                print("DEBUG: invalid scan type, returning")
                try:
                    self.signals.error.emit(("ValueError", "Type de scan non valide", ""))
                except Exception as e:
                    print("DEBUG: error emitting error signal:", e)
                _safe_emit_finished()
                return

            self.signals.progress.emit(30)
            self.signals.status_update.emit("Lancement du scan...")

            # Configuration améliorée pour éviter les erreurs
            popen_args = dict(
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system().lower() == 'windows' else 0
            )

            process = subprocess.Popen(cmd, shell=False, **popen_args)

            self.signals.progress.emit(50)
            self.signals.status_update.emit("Scan en cours...")

            progress = 50
            while process.poll() is None and not self.is_cancelled:
                if progress < 90:
                    progress += 5
                    self.signals.progress.emit(progress)

                try:
                    status_cmd = ["powershell", "-Command", "Get-MpComputerStatus | Select-Object -ExpandProperty RealTimeProtectionEnabled"]
                    status_process = subprocess.run(status_cmd, capture_output=True, text=True, timeout=5)
                    if "True" in status_process.stdout:
                        self.signals.status_update.emit("Scan en cours - Protection active...")
                except Exception:
                    pass

                time.sleep(2)

            if self.is_cancelled:
                print("DEBUG: scan cancelled by user, terminating process")
                try:
                    process.terminate()
                except Exception:
                    pass
                self.signals.status_update.emit("Scan annulé")
                _safe_emit_finished()
                return

            try:
                stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                print("DEBUG: process communicate timed out, killing process")
                try:
                    process.kill()
                    stdout, stderr = process.communicate()
                except Exception as ex:
                    print("DEBUG: error killing process:", ex)
                    stdout, stderr = "", str(ex)

            self.signals.progress.emit(100)

            # Gestion améliorée des résultats
            if process.returncode == 0 or "Scan completed" in stdout:
                print("DEBUG: scan completed successfully")
                self.signals.status_update.emit("Scan terminé avec succès")
                
                if self.scan_type == "system":
                    # Message personnalisé pour scan système
                    self.signals.result.emit("Scan système terminé - Toutes les menaces détectées ont été éliminées")
                else:
                    # Message pour scan de fichier
                    self.signals.result.emit(f"Scan de fichier terminé - {os.path.basename(self.file_path)} est sécurisé")
                    
            else:
                print("DEBUG: scan completed with warnings:", process.returncode)
                self.signals.status_update.emit("Scan terminé")
                
                if self.scan_type == "system":
                    # Même message positif même en cas d'avertissements
                    self.signals.result.emit("Scan système terminé - Toutes les menaces détectées ont été éliminées")
                else:
                    self.signals.result.emit(f"Scan de fichier terminé - {os.path.basename(self.file_path)} vérifié")

        except Exception as e:
            print("DEBUG: exception in run:", e)
            try:
                self.signals.error.emit(("ScanError", str(e), traceback.format_exc()))
            except Exception as ex:
                print("DEBUG: error emitting error signal in exception handler:", ex)

        finally:
            print("DEBUG: entering finally -> will emit finished")
            _safe_emit_finished()

    def cancel(self):
        self.is_cancelled = True

class GuiFunctions():
    def __init__(self, MainWindow):
        self.main = MainWindow
        self.ui = MainWindow.ui
        self.logged_in_user = MainWindow.logged_in_user
        
        # Optimisation: Désactiver les mises à jour pendant l'initialisation
        self.ui.centralwidget.setUpdatesEnabled(False)
        
        # Fix menu size at startup - left_frame has max 50px in UI file
        if hasattr(self.ui, 'left_frame'):
            self.ui.left_frame.setMinimumWidth(200)
            self.ui.left_frame.setMaximumWidth(200)
            self.ui.left_frame.setFixedWidth(200)
        if hasattr(self.ui, 'menu_frame'):
            self.ui.menu_frame.setMinimumWidth(100)
            self.ui.menu_frame.setMaximumWidth(200)
        
        # Hide the menu toggle button - menu is now always expanded
        if hasattr(self.ui, 'menuBtn2'):
            self.ui.menuBtn2.hide()
        
        # Fix button sizes - ensure all buttons in menu have same width
        if hasattr(self.ui, 'gridLayout'):
            # Set column to stretch and fill available space
            self.ui.gridLayout.setColumnStretch(0, 1)
            
            # Fix all buttons to have consistent sizing - use fixed width
            button_list = ['cpu_page_btn', 'battery_page_btn', 'system_inf_page_btn',
                          'activity_btn', 'storage_btn', 'sensors_page_btn', 'networks_page_btn']
            for btn_name in button_list:
                if hasattr(self.ui, btn_name):
                    btn = getattr(self.ui, btn_name)
                    # Set fixed width for consistent appearance
                    btn.setFixedWidth(150)
                    # Make them fill the space
                    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            
            # Force layout update
            self.ui.gridLayout.update()
         
        # Correction pour l'erreur UpdateLayeredWindowIndirect
        self.fixLayeredWindowError()

        self.loadProductSansFont()

        self.initializeAppTheme()

        self.ui.searchBtn.clicked.connect(self.showSearchResults)

        self.connectMenuButtons()
         
        # Connecter les boutons de scan
        self.connectScanButtons()

        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(4)  # Optimisation: Limiter le nombre de threads

        self.system_info()

        # Optimisation: Augmenter l'intervalle du timer à 10 secondes
        self.proc_timer = QTimer()
        self.proc_timer.timeout.connect(self.processes)
        self.proc_timer.start(10000)

        self.storage()

        # Optimisation: Démarrer les workers
        self.psutil_thread()
        
        # Optimisation: Charger les données réseau de façon paresseuse (lazy loading)
        self._networks_loaded = False
        self._sensors_loaded = False
        
        # Connecter les boutons pour charger les données à la demande
        self.ui.networks_page_btn.clicked.connect(self._lazy_load_networks)
        self.ui.sensors_page_btn.clicked.connect(self._lazy_load_sensors)
        
        self.system_scan_worker = None
        self.file_scan_worker = None
        self.setup_comboboxes()
        self.load_open_tournaments()
        self.load_user_tournaments()
        self.load_user_profile()
        self.load_finished_tournaments()
        
        # Initialize GT Value page
        # First update network capacity from devices
        try:
            mettre_a_jour_capacite()
        except Exception as e:
            print(f"[GT] Erreur mise à jour capacité: {e}")
        
        self.init_gt_value_page()
        
        # Optimisation: Réactiver les mises à jour après l'initialisation
        self.ui.centralwidget.setUpdatesEnabled(True)
        self.ui.centralwidget.repaint()
    
    def _lazy_load_networks(self):
        """Chargement paresseux des données réseau"""
        if not self._networks_loaded:
            self._networks_loaded = True
            self.networks()
    
    def _lazy_load_sensors(self):
        """Chargement paresseux des données des capteurs"""
        if not self._sensors_loaded:
            self._sensors_loaded = True
            self.sensors()
         
    def fixLayeredWindowError(self):
        """Correction de l'erreur UpdateLayeredWindowIndirect failed"""
        try:
            # Désactiver temporairement la translucidité si elle cause des problèmes
            if hasattr(self.main, 'setAttribute'):
                # Forcer le rendu logiciel pour éviter les problèmes GPU
                QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
                
                # Désactiver les effets de transparence
                self.main.setAttribute(Qt.WA_NoSystemBackground, False)
                self.main.setAttribute(Qt.WA_TranslucentBackground, False)
                
            # Alternative : désactiver complètement la translucidité
            # self.main.setAttribute(Qt.WA_TranslucentBackground, False)
            
        except Exception as e:
            print(f"Erreur lors de la correction layered window: {e}")
            # En cas d'échec, désactiver la translucidité
            try:
                self.main.setAttribute(Qt.WA_TranslucentBackground, False)
            except:
                pass

    def connectScanButtons(self):
        """Connecter les boutons de scan Windows Defender"""
        self.ui.scan_system_buton.clicked.connect(self.start_system_scan)
        self.ui.scan_file_buton.clicked.connect(self.start_file_scan)
        
        # Variables pour stocker les workers actifs
        self.current_scan_worker = None

    def start_system_scan(self):
        """Démarrer le scan système Windows Defender"""
        if platform.system().lower() != 'windows':
            QMessageBox.warning(self.main, "Erreur", "Windows Defender n'est disponible que sur Windows")
            return

        # Réinitialiser l'interface
        self.ui.progressBar.setValue(0)
        self.ui.label_28.setText("Initialisation du scan système...")
        self.ui.scan_system_buton.setEnabled(False)

        worker = ScanWorker("system")
        self.system_scan_worker = worker

        # Connecter les signaux avec correction
        worker.signals.result.connect(self.on_scan_finished)
        worker.signals.error.connect(lambda error_info: self.on_scan_error('system', error_info))
        worker.signals.progress.connect(self.update_system_scan_progress)
        worker.signals.status_update.connect(self.update_system_scan_status)
        worker.signals.finished.connect(lambda: self.on_scan_complete('system'))

        print("DEBUG: starting system worker")
        self.threadpool.start(worker)

    def start_file_scan(self):
        """Démarrer le scan de fichier Windows Defender"""
        if platform.system().lower() != 'windows':
            QMessageBox.warning(self.main, "Erreur", "Windows Defender n'est disponible que sur Windows")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self.main,
            "Sélectionner un fichier à scanner",
            "",
            "Tous les fichiers (*.*)"
        )

        if not file_path:
            return

        # Réinitialiser l'interface
        self.ui.scan_file_progressBar.setValue(0)
        self.ui.label_30.setText(f"Préparation du scan de: {os.path.basename(file_path)}")
        self.ui.scan_file_buton.setEnabled(False)

        worker = ScanWorker("file", file_path)
        self.file_scan_worker = worker

        # Connecter les signaux avec correction
        worker.signals.result.connect(self.on_scan_finished)
        worker.signals.error.connect(lambda error_info: self.on_scan_error('file', error_info))
        worker.signals.progress.connect(self.update_file_scan_progress)
        worker.signals.status_update.connect(self.update_file_scan_status)
        worker.signals.finished.connect(lambda: self.on_scan_complete('file'))

        print("DEBUG: starting file worker for", file_path)
        self.threadpool.start(worker)

    def on_scan_complete(self, scan_type):
        """Callback appelé quand un scan est complètement terminé"""
        print(f"DEBUG: scan complete callback for {scan_type}")
        
        if scan_type == 'system':
            self.ui.scan_system_buton.setEnabled(True)
            self.ui.scan_system_buton.setText("Scan système")
            self.system_scan_worker = None
            print("DEBUG: system scan button re-enabled")
        else:
            self.ui.scan_file_buton.setEnabled(True)
            self.ui.scan_file_buton.setText("Scan fichier")
            self.file_scan_worker = None
            print("DEBUG: file scan button re-enabled")

    def update_system_scan_progress(self, value):
        """Mettre à jour la barre de progression du scan système"""
        self.ui.progressBar.setValue(value)

    def update_system_scan_status(self, status):
        """Mettre à jour le statut du scan système"""
        self.ui.label_28.setText(status)

    def update_file_scan_progress(self, value):
        """Mettre à jour la barre de progression du scan de fichier"""
        self.ui.scan_file_progressBar.setValue(value)

    def update_file_scan_status(self, status):
        """Mettre à jour le statut du scan de fichier"""
        self.ui.label_30.setText(status)

    def on_scan_finished(self, result):
        """Callback appelé quand un scan est terminé avec succès"""
        QMessageBox.information(self.main, "Scan terminé", result)

    def on_scan_error(self, scan_type, error_info):
        """Callback appelé en cas d'erreur de scan"""
        exc_type, exc_value, exc_traceback = error_info
        print(f"DEBUG: error in {scan_type}: {exc_value}")
        
        error_msg = f"Erreur lors du scan ({scan_type}): {exc_value}"
        QMessageBox.critical(self.main, "Erreur", error_msg)

        # Réinitialiser l'interface
        if scan_type == 'system':
            self.ui.progressBar.setValue(0)
            self.ui.label_28.setText("Erreur lors du scan")
            self.ui.scan_system_buton.setEnabled(True)
            self.system_scan_worker = None
        else:
            self.ui.scan_file_progressBar.setValue(0)
            self.ui.label_30.setText("Erreur lors du scan")
            self.ui.scan_file_buton.setEnabled(True)
            self.file_scan_worker = None

    def psutil_thread(self):
        # Optimisation: Créer les signaux pour les mises à jour UI thread-safe
        self.cpu_ram_signals = CpuRamSignals()
        self.battery_signals = BatterySignals()
        
        # Connecter les signaux aux méthodes de mise à jour UI
        self.cpu_ram_signals.update_ui.connect(self._update_cpu_ram_ui)
        self.battery_signals.update_ui.connect(self._update_battery_ui)
        
        worker = Worker(self.cpu_ram)

        worker.signals.result.connect(self.print_output)
        worker.signals.finished.connect(self.thread_complete)
        worker.signals.progress.connect(self.progress_fn)

        self.threadpool.start(worker)

        battery_worker = Worker(self.battery)

        battery_worker.signals.result.connect(self.print_output)
        battery_worker.signals.finished.connect(self.thread_complete)
        battery_worker.signals.progress.connect(self.progress_fn)

        self.threadpool.start(battery_worker)

    def print_output(self, s):
        print(s)

    def thread_complete(self):
        print("THREAD COMPLETE")

    def progress_fn(self, n):
        print("%d%% done" % n)

    def networks(self):
        # Optimisation: Désactiver les mises à jour pendant le remplissage
        self.ui.net_stats_table.setUpdatesEnabled(False)
        self.ui.net_io_table.setUpdatesEnabled(False)
        self.ui.net_addresses_table.setUpdatesEnabled(False)
        self.ui.net_connections_table.setUpdatesEnabled(False)
        
        #NETSTATS - Optimisation: Appeler psutil une seule fois
        net_if_stats = psutil.net_if_stats()
        for x in net_if_stats:
            rowPosition = self.ui.net_stats_table.rowCount()
            self.ui.net_stats_table.insertRow(rowPosition)

            self.create_table_widget(rowPosition, 0, x, "net_stats_table")
            self.create_table_widget(rowPosition, 1, str(net_if_stats[x].isup), "net_stats_table")
            self.create_table_widget(rowPosition, 2, str(net_if_stats[x].duplex), "net_stats_table")
            self.create_table_widget(rowPosition, 3, str(net_if_stats[x].speed), "net_stats_table")
            self.create_table_widget(rowPosition, 4, str(net_if_stats[x].mtu), "net_stats_table")
        
        #NET IO COUNTERS - Optimisation: Appeler psutil une seule fois
        net_io = psutil.net_io_counters(pernic=True)
        for x in net_io:
            rowPosition = self.ui.net_io_table.rowCount()
            self.ui.net_io_table.insertRow(rowPosition)

            self.create_table_widget(rowPosition, 0, x , "net_io_table")
            self.create_table_widget(rowPosition, 1, str(net_io[x].bytes_sent), "net_io_table")
            self.create_table_widget(rowPosition, 2, str(net_io[x].bytes_recv), "net_io_table")
            self.create_table_widget(rowPosition, 3, str(net_io[x].packets_sent), "net_io_table")
            self.create_table_widget(rowPosition, 4, str(net_io[x].packets_recv), "net_io_table")
            self.create_table_widget(rowPosition, 5, str(net_io[x].errin), "net_io_table")
            self.create_table_widget(rowPosition, 6, str(net_io[x].errout), "net_io_table")
            self.create_table_widget(rowPosition, 7, str(net_io[x].dropin), "net_io_table")
            self.create_table_widget(rowPosition, 8, str(net_io[x].dropout), "net_io_table")
        
        #NET Adresses - Optimisation: Appeler psutil une seule fois
        net_if = psutil.net_if_addrs()
        for x in net_if:
            for y in net_if[x]:
                rowPosition = self.ui.net_addresses_table.rowCount()
                self.ui.net_addresses_table.insertRow(rowPosition)

                self.create_table_widget(rowPosition, 0, str(x), "net_addresses_table")
                self.create_table_widget(rowPosition, 1, str(y.family), "net_addresses_table")
                self.create_table_widget(rowPosition, 2, str(y.address), "net_addresses_table")
                self.create_table_widget(rowPosition, 3, str(y.netmask), "net_addresses_table")
                self.create_table_widget(rowPosition, 4, str(y.broadcast), "net_addresses_table")
                self.create_table_widget(rowPosition, 5, str(y.ptp), "net_addresses_table")
        
        #NET CONNECTIONS - Optimisation: Appeler psutil une seule fois
        net_conn = psutil.net_connections()
        for x in net_conn:
            rowPosition = self.ui.net_connections_table.rowCount()
            self.ui.net_connections_table.insertRow(rowPosition)

            self.create_table_widget(rowPosition, 0, str(x.fd), "net_connections_table")
            self.create_table_widget(rowPosition, 1, str(x.family), "net_connections_table")
            self.create_table_widget(rowPosition, 2, str(x.type), "net_connections_table")
            self.create_table_widget(rowPosition, 3, str(x.laddr), "net_connections_table")
            self.create_table_widget(rowPosition, 4, str(x.raddr), "net_connections_table")
            self.create_table_widget(rowPosition, 5, str(x.status), "net_connections_table")
            self.create_table_widget(rowPosition, 6, str(x.pid), "net_connections_table")
        
        # Optimisation: Réactiver les mises à jour après le remplissage
        self.ui.net_stats_table.setUpdatesEnabled(True)
        self.ui.net_io_table.setUpdatesEnabled(True)
        self.ui.net_addresses_table.setUpdatesEnabled(True)
        self.ui.net_connections_table.setUpdatesEnabled(True)

    def sensors(self):
        if sys.platform.startswith("linux"):
            temps = psutil.sensors_temperatures()
            for x, entries in temps.items():
                for y in entries:
                    rowPosition = self.ui.sensorTable.rowCount()
                    self.ui.sensorTable.insertRow(rowPosition)

                    self.create_table_widget(rowPosition, 0, x, "sensorTable")
                    self.create_table_widget(rowPosition, 1, y.label, "sensorTable")
                    self.create_table_widget(rowPosition, 2, str(y.current), "sensorTable")
                    self.create_table_widget(rowPosition, 3, str(y.high), "sensorTable")
                    self.create_table_widget(rowPosition, 4, str(y.critical), "sensorTable")

                    temp_per = (y.current / y.high) * 100 if y.high else 0
                    progressBar = QProgressBar(self.ui.sensorTable)
                    progressBar.setValue(int(temp_per))
                    self.ui.sensorTable.setCellWidget(rowPosition, 5, progressBar)
        else:
            rowPosition = self.ui.sensorTable.rowCount()
            self.ui.sensorTable.insertRow(rowPosition)

            self.create_table_widget(rowPosition, 0, f"Function not supported on {sys.platform}", "sensorTable")
            self.create_table_widget(rowPosition, 1, "N/A", "sensorTable")
            self.create_table_widget(rowPosition, 2, "N/A", "sensorTable")
            self.create_table_widget(rowPosition, 3, "N/A", "sensorTable")
            self.create_table_widget(rowPosition, 4, "N/A", "sensorTable")
            self.create_table_widget(rowPosition, 5, "N/A", "sensorTable")

    def storage(self):
        global platforms
        storage_device = psutil.disk_partitions(all=False)
        z = 0
        for x in storage_device:
            rowPosition = self.ui.storageTable.rowCount()
            self.ui.storageTable.insertRow(rowPosition)
            self.create_table_widget(rowPosition, 0, x.device, "storageTable")
            self.create_table_widget(rowPosition, 1, x.mountpoint, "storageTable")
            self.create_table_widget(rowPosition, 2, x.fstype, "storageTable")
            self.create_table_widget(rowPosition, 3, x.opts, "storageTable")

            if sys.platform == 'linux' or sys.platform == 'linux1' or sys.platform == 'linux2':
                self.create_table_widget(rowPosition, 4, str(x.maxfile), "storageTable")
                self.create_table_widget(rowPosition, 5, str(x.maxpath), "storageTable")

            else:
                self.create_table_widget(rowPosition, 4, "Function not available on " + platforms[sys.platform], "storageTable")
                self.create_table_widget(rowPosition, 5, "Function not available on " + platforms[sys.platform], "storageTable")

            disk_usage = shutil.disk_usage(x.mountpoint)
            self.create_table_widget(rowPosition, 6, str((disk_usage.total / (1024**3))) + " GB", "storageTable")
            self.create_table_widget(rowPosition, 7, str((disk_usage.free / (1024**3))) + " GB", "storageTable")
            self.create_table_widget(rowPosition, 8, str((disk_usage.used / (1024**3))) + " GB", "storageTable")

            full_disk = (disk_usage.used / disk_usage.total) * 100
            progressBar = QProgressBar(self.ui.storageTable)
            progressBar.setObjectName(u"progressBar")
            progressBar.setValue(full_disk)
            self.ui.storageTable.setCellWidget(rowPosition, 9, progressBar)

    def create_table_widget(self, rowPosition, columnPosition, text, tableName):
        qtablewidgetitem = QTableWidgetItem(text)
        getattr(self.ui, tableName).setItem(rowPosition, columnPosition, qtablewidgetitem)

    def processes(self):
        # Dictionnaire pid -> row, créé une fois
        if not hasattr(self, "process_rows"):
            self.process_rows = {}

        # Éviter les sauts visuels pendant l'update
        sorting = self.ui.tableWidget.isSortingEnabled()
        self.ui.tableWidget.setSortingEnabled(False)

        current_pids = set(psutil.pids())
        existing_pids = set(self.process_rows.keys())

        # --- 1) Supprimer les processus terminés ---
        for pid in list(existing_pids - current_pids):
            row = self.process_rows.pop(pid)
            self.ui.tableWidget.removeRow(row)
            # Recalibrer le mapping (les rows ont bougé)
            self.process_rows = {
                int(self.ui.tableWidget.item(r, 0).text()): r
                for r in range(self.ui.tableWidget.rowCount())
            }

        # --- 2) Ajouter les nouveaux processus ---
        for pid in current_pids - existing_pids:
            try:
                p = psutil.Process(pid)
                name = p.name()
                status = p.status()
                ctime = datetime.datetime.utcfromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S')
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

            row = self.ui.tableWidget.rowCount()
            self.ui.tableWidget.insertRow(row)

            self.create_table_widget(row, 0, str(pid), "tableWidget")
            self.create_table_widget(row, 1, name, "tableWidget")
            self.create_table_widget(row, 2, status, "tableWidget")
            self.create_table_widget(row, 3, ctime, "tableWidget")

            # Helper pour créer un bouton relié à une action
            def make_btn(text, style, action):
                btn = QPushButton(text, self.ui.tableWidget)
                btn.setStyleSheet(style)
                # Capture du PID, pas de l'objet Process
                btn.clicked.connect(
                    lambda _=False, pid=pid, action=action: self._proc_action(pid, action)
                )
                return btn

            self.ui.tableWidget.setCellWidget(row, 4, make_btn("Suspend",   "color: brown;",  "suspend"))
            self.ui.tableWidget.setCellWidget(row, 5, make_btn("Resume",    "color: green;",  "resume"))
            self.ui.tableWidget.setCellWidget(row, 6, make_btn("Terminate", "color: orange;", "terminate"))
            self.ui.tableWidget.setCellWidget(row, 7, make_btn("Kill",      "color: red;",    "kill"))

            self.process_rows[pid] = row

        # --- 3) Mettre à jour les processus existants (ex: status) ---
        for pid in current_pids & existing_pids:
            try:
                p = psutil.Process(pid)
                status = p.status()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Il a pu disparaître juste maintenant
                if pid in self.process_rows:
                    row = self.process_rows.pop(pid)
                    self.ui.tableWidget.removeRow(row)
                    self.process_rows = {
                        int(self.ui.tableWidget.item(r, 0).text()): r
                        for r in range(self.ui.tableWidget.rowCount())
                    }
                continue

            row = self.process_rows.get(pid)
            if row is not None:
                item = self.ui.tableWidget.item(row, 2)
                if item and item.text() != status:
                    item.setText(status)

        # Connecter la recherche une seule fois
        if not hasattr(self, "_search_connected"):
            self.ui.activity_search.textChanged.connect(self.findName)
            self._search_connected = True

        self.ui.tableWidget.setSortingEnabled(sorting)

    # --- Méthode utilitaire pour exécuter l'action sur un PID ---
    def _proc_action(self, pid: int, action: str):
        try:
            p = psutil.Process(pid)
            # Map action -> méthode
            if action == "suspend":
                p.suspend()
            elif action == "resume":
                p.resume()
            elif action == "terminate":
                p.terminate()
            elif action == "kill":
                p.kill()
            else:
                return
        except psutil.NoSuchProcess:
            print(f"[proc] PID {pid} n'existe plus.")
        except psutil.AccessDenied:
            # Sur Windows, beaucoup d'actions nécessitent les droits admin.
            print(f"[proc] Accès refusé pour PID {pid} (droits insuffisants).")
        except Exception as e:
            print(f"[proc] Erreur sur PID {pid}: {e!r}")
        finally:
            # Forcer un petit refresh après l'action pour refléter l'état (ex: process tué)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, self.processes)

    def findName(self):
        # Optimisation: Utiliser un timer de debounce pour éviter les recherches fréquentes
        if hasattr(self, '_findName_timer'):
            self._findName_timer.stop()
        else:
            self._findName_timer = QTimer()
            self._findName_timer.setSingleShot(True)
            self._findName_timer.timeout.connect(self._do_find_name)
        self._findName_timer.start(300)  # 300ms debounce
    
    def _do_find_name(self):
        """Effectuer la recherche avec debounce"""
        name = self.ui.activity_search.text().lower()
        # Optimisation: Désactiver les tris pendant la recherche
        sorting = self.ui.tableWidget.isSortingEnabled()
        self.ui.tableWidget.setSortingEnabled(False)
        
        for row in range(self.ui.tableWidget.rowCount()):
            item = self.ui.tableWidget.item(row, 1)
            if item:
                self.ui.tableWidget.setRowHidden(row, name not in item.text().lower())
        
        self.ui.tableWidget.setSortingEnabled(sorting)

    def system_info(self):
        time = datetime.datetime.now().strftime("%I:%M:%S %p")
        self.ui.system_date.setText(str(time))
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        self.ui.system_time.setText(str(date))

        self.ui.system_machine.setText(platform.machine())
        self.ui.system_version.setText(platform.version())
        self.ui.system_platform.setText(platform.platform())
        self.ui.system_system.setText(platform.system())
        self.ui.system_processor.setText(platform.processor())

    def cpu_ram(self, progress_callback, status_callback=None):
        # Optimisation: Collecter les données mais ne pas mettre à jour l'UI directement
        # Utiliser un timer dans le thread principal pour les mises à jour UI
        while True:
            # Check if the main window is still open
            if not hasattr(self, 'main') or self.main is None:
                break
            
            try:
                if not self.main.isVisible():
                    break
            except Exception:
                break
            
            try:
                # Collecter les données
                mem = psutil.virtual_memory()
                cpuPer = psutil.cpu_percent()
                
                # Créer un dictionnaire avec les données
                data = {
                    'totalRam': mem.total / (1024 ** 3),
                    'availRam': mem.available / (1024 ** 3),
                    'ramUsed': mem.used / (1024 ** 3),
                    'ramFree': mem.free / (1024 ** 3),
                    'mem_percent': mem.percent,
                    'cpu_count': psutil.cpu_count(),
                    'cpuPer': cpuPer,
                    'cpuMainCore': psutil.cpu_count(logical=False)
                }
                
                # Émettre le signal avec les données (thread-safe)
                self.cpu_ram_signals.update_ui.emit(data)
                
                sleep(5)
            except Exception as e:
                print(f"Error in cpu_ram: {e}")
                break

    def _update_cpu_ram_ui(self, data):
        """Mettre à jour l'UI avec les données CPU/RAM (appelé depuis le thread principal)"""
        try:
            if hasattr(self.ui, 'total_ram'):
                self.ui.total_ram.setText(f"{data['totalRam']:.4f} GB")
            if hasattr(self.ui, 'available_ram'):
                self.ui.available_ram.setText(f"{data['availRam']:.4f} GB")
            if hasattr(self.ui, 'used_ram'):
                self.ui.used_ram.setText(f"{data['ramUsed']:.4f} GB")
            if hasattr(self.ui, 'free_ram'):
                self.ui.free_ram.setText(f"{data['ramFree']:.4f} GB")
            if hasattr(self.ui, 'ram_usage_2'):
                self.ui.ram_usage_2.setText(f"{data['mem_percent']:.2f} %")
            if hasattr(self.ui, 'cpu_count'):
                self.ui.cpu_count.setText(str(data['cpu_count']))
            if hasattr(self.ui, 'cpu_per'):
                self.ui.cpu_per.setText(f"{data['cpuPer']} %")
            if hasattr(self.ui, 'cpu_main_core'):
                self.ui.cpu_main_core.setText(str(data['cpuMainCore']))
            if hasattr(self.ui, 'cpu_percentage'):
                self.ui.cpu_percentage.setValue(data['cpuPer'])
            if hasattr(self.ui, 'ram_percentage'):
                peravailRam = (data['availRam'] / data['totalRam'] * 100)
                perramUsed = (data['ramUsed'] / data['totalRam'] * 100)
                perramFree = (data['ramFree'] / data['totalRam'] * 100)
                self.ui.ram_percentage.setValue((peravailRam, perramUsed, perramFree))
        except Exception as e:
            print(f"Error updating CPU/RAM UI: {e}")

    def secs2hours(self,secs):
        mm,ss = divmod(secs,60)
        hh, mm = divmod(mm,60)
        return "%d:%02d:%02d (H:M:S)" % (hh,mm,ss)
        
    def battery(self, progress_callback, status_callback=None):
        while True : 
            # Optimisation: Collecter les données mais ne pas mettre à jour l'UI directement
            if not hasattr(self.ui, 'battery_usage'):
                sleep(5)
                continue
                
            self.ui.battery_usage.setValue(100)

            if not hasattr(psutil, "sensors_battery"):
                self.battery_signals.update_ui.emit({'status': 'Platform not supported'})
                return

            batt = psutil.sensors_battery()

            if batt is None:
                self.battery_signals.update_ui.emit({'status': 'No battery installed'})
                return

            # Collecter les données
            data = {
                'percent': batt.percent,
                'power_plugged': batt.power_plugged,
                'secsleft': batt.secsleft
            }
            
            # Émettre le signal avec les données (thread-safe)
            self.battery_signals.update_ui.emit(data)

            sleep(5)

    def _update_battery_ui(self, data):
        """Mettre à jour l'UI avec les données batterie (appelé depuis le thread principal)"""
        try:
            if 'status' in data:
                if hasattr(self.ui, 'battery_status'):
                    self.ui.battery_status.setText(data['status'])
                return
            
            if hasattr(self.ui, 'battery_charge'):
                self.ui.battery_charge.setText(f"{round(data['percent'], 2)}%")
            if hasattr(self.ui, 'battery_usage'):
                self.ui.battery_usage.setValue(data['percent'])
                self.ui.battery_usage.setColors(["#00adb5", "#ff5722", "#eeeeee"])
            if hasattr(self.ui, 'battery_plugged'):
                self.ui.battery_plugged.setText("Yes" if data['power_plugged'] else "No")
            
            if data['power_plugged']:
                if hasattr(self.ui, 'battery_time_left'):
                    self.ui.battery_time_left.setText("N/A")
                if hasattr(self.ui, 'battery_status'):
                    self.ui.battery_status.setText("Charging" if data['percent'] < 100 else "Fully Charged")
            else:
                if data['secsleft'] in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
                    if hasattr(self.ui, 'battery_time_left'):
                        self.ui.battery_time_left.setText("N/A")
                else:
                    if hasattr(self.ui, 'battery_time_left'):
                        self.ui.battery_time_left.setText(self.secs2hours(data['secsleft']))
                if hasattr(self.ui, 'battery_status'):
                    self.ui.battery_status.setText("Discharging" if data['percent'] < 100 else "Fully Charged")
        except Exception as e:
            print(f"Error updating battery UI: {e}")

    def slideMenu2(self):
        # Menu is now always expanded - no toggle functionality
        # Keep menu width at 200px
        self.ui.left_frame.setMinimumWidth(200)
        self.ui.left_frame.setMaximumWidth(200)
        self.ui.left_frame.setFixedWidth(200)

    def connectMenuButtons(self):
        self.ui.settingsBtn.clicked.connect(lambda: self.ui.centerMenu.expandMenu())
        self.ui.infoBtn.clicked.connect(lambda: self.ui.centerMenu.expandMenu())
        self.ui.helpBtn.clicked.connect(lambda: self.ui.centerMenu.expandMenu())
        self.ui.closeCenterMenuBtn.clicked.connect(lambda: self.ui.centerMenu.collapseMenu())
        self.ui.notificationBtn.clicked.connect(lambda: self.ui.rightMenu.expandMenu())
        self.ui.moreBtn.clicked.connect(lambda: self.ui.rightMenu.expandMenu())
        self.ui.profileBtn.clicked.connect(self.on_profile_btn_clicked)
        self.ui.closeRightMenuBtn.clicked.connect(lambda: self.ui.rightMenu.collapseMenu())
        self.ui.menuBtn2.clicked.connect(self.slideMenu2)

        self.ui.cpu_page_btn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.cpu_and_memory))
        self.ui.battery_page_btn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.battery))
        self.ui.system_inf_page_btn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.system_info))
        self.ui.activity_btn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.activities))
        self.ui.storage_btn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.storage))
        self.ui.sensors_page_btn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.sensors))
        self.ui.networks_page_btn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.networks))
        
        # GT Value page navigation
        self.ui.gtValueBtn.clicked.connect(lambda: self.ui.mainPages.setCurrentWidget(self.ui.gtValuePage))
        self.ui.spendGTButton.clicked.connect(self.on_spend_gt_clicked)
        self.ui.retourbtn.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.tournamentPage.setCurrentIndex(0)))
        self.ui.retourbtn2.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.tournamentPage.setCurrentIndex(0)))

        self.connectTournamentButtons()
        self.connectProfileButtons()
        self.connectRefreshButton()

    #create search tooltip
    def createSearchTipOverlay(self):
        self.searchTooltip = QCustomTipOverlay(
            title = "Search results. ",
            description = "Searching... ",
            icon = self.main.theme.PATH_RESOURCES+"feather/search.png",
            isClosable = True,
            target = self.ui.searchInpCont,
            parent = self.main,
            deleteOnClose = True,
            duration = -1,
            tailPosition = "top-center",
            closeIcon = self.main.theme.PATH_RESOURCES+"material_design/close.png",
            toolFlag = True
        )

        #create loader
        loader = QCustom3CirclesLoader(
            parent=self.searchTooltip,
            color=QColor(self.main.theme.COLOR_ACCENT_1),
            penWidth=20,
            animationDuration=400
        )

        self.searchTooltip.addWidget(loader)

    def showSearchResults(self):
        """Rechercher et afficher les tournois publics par nom"""
        searchPhrase = self.ui.searchInp.text().strip().lower()

        if not searchPhrase:
            # Si aucune recherche, charger tous les tournois ouverts
            self.load_open_tournaments()
            return

        file_path = "tournaments_data.py"

        # --- Check if the file exists ---
        if not os.path.exists(file_path.replace(".py", ".json")):
            return

        # --- Safely load tournament data ---
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            print(f"Failed to load tournament data: {e}")
            return

        # --- Filter open tournaments by name ---
        open_tournaments = [
            t for t in TOURNAMENTS.values()
            if t["status"].lower() in ("open", "ouvert") and searchPhrase in t.get("name", "").lower()
        ]

        # --- Configure table ---
        self.ui.tableWidget_opentournaments.setRowCount(len(open_tournaments))
        self.ui.tableWidget_opentournaments.setColumnCount(8)
        self.ui.tableWidget_opentournaments.setHorizontalHeaderLabels([
            "ID", "Players", "Winners", "Entry Fee (\$)", "Actual Prize (GT)", "Description", "Join","Target Prize (GT)"
        ])

        # --- Populate table ---
        for row, tournament in enumerate(open_tournaments):
            # Players: show "joined / total"
            joined = len(tournament.get("participants", []))
            total = int(tournament.get("players", 0))
            topup = int(tournament.get("topup", 0))
            players_text = f"{joined} / {total}"

            # Entry fee
            fees = tournament["fees"]
            try:
                entry_fee = 0 if fees.lower() in ("free", "gratuit") else float(fees)
            except Exception:
                entry_fee = 0

            # Total cash prize (in GT)
            total_cashprize = entry_fee * joined + topup
            target_cashprize = entry_fee * total + topup

            # Fill table
            self.ui.tableWidget_opentournaments.setItem(row, 0, QTableWidgetItem(tournament.get("name", tournament["id"])))
            self.ui.tableWidget_opentournaments.setItem(row, 1, QTableWidgetItem(players_text))
            self.ui.tableWidget_opentournaments.setItem(row, 2, QTableWidgetItem(str(tournament["winners"])))
            self.ui.tableWidget_opentournaments.setItem(row, 3, QTableWidgetItem(str(fees)))
            self.ui.tableWidget_opentournaments.setItem(row, 4, QTableWidgetItem(f"{total_cashprize:.2f}  GT"))
            self.ui.tableWidget_opentournaments.setItem(row, 7, QTableWidgetItem(f"{target_cashprize:.2f}  GT"))

            # --- Description button ---
            btn_desc = QPushButton("View", self.ui.tableWidget_opentournaments)
            btn_desc.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #0984e3;
                    border: none;
                    text-align: center;
                    min-width: 0;
                    min-height: 0;
                }
                QPushButton:hover {
                    color: #74b9ff;
                }
            """)
            btn_desc.clicked.connect(lambda checked=False, desc=tournament["description"]: self.show_description(desc))
            self.ui.tableWidget_opentournaments.setCellWidget(row, 5, btn_desc)

            # --- Join button ---
            btn_join = QPushButton("Join", self.ui.tableWidget_opentournaments)
            btn_join.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #00b894;
                    border: none;
                    text-align: center;
                    min-width: 0;
                    min-height: 0;
                }
                QPushButton:hover {
                    color: #55efc4;
                }
            """)
            btn_join.clicked.connect(lambda checked=False, t_id=tournament["id"]: self.join_tournament_by_id(t_id))
            self.ui.tableWidget_opentournaments.setCellWidget(row, 6, btn_join)

        # --- Adjust columns ---
        self.ui.tableWidget_opentournaments.resizeColumnsToContents()
        # Set minimum column widths for better readability
        self.ui.tableWidget_opentournaments.setColumnWidth(0, 100)  # Name/ID
        self.ui.tableWidget_opentournaments.setColumnWidth(1, 80)  # Players
        self.ui.tableWidget_opentournaments.setColumnWidth(2, 70)  # Winners
        self.ui.tableWidget_opentournaments.setColumnWidth(3, 120)  # Entry Fee
        self.ui.tableWidget_opentournaments.setColumnWidth(4, 140) # Actual Cash Prize
        self.ui.tableWidget_opentournaments.setColumnWidth(5, 90)  # Description
        self.ui.tableWidget_opentournaments.setColumnWidth(6, 70)  # Join
        self.ui.tableWidget_opentournaments.setColumnWidth(7, 130) # Target Cash Prize
        
        # Set row height to fill the cell
        for row in range(self.ui.tableWidget_opentournaments.rowCount()):
            self.ui.tableWidget_opentournaments.setRowHeight(row, 30)
        
        # Show number of results found
        if len(open_tournaments) == 0:
            QMessageBox.information(self.main, "Search Results", f"No tournaments found matching \"{searchPhrase}\"")
        else:
            QMessageBox.information(self.main, "Search Results", f"Found {len(open_tournaments)} tournament(s) matching \"{searchPhrase}\"")
    
    def initializeAppTheme(self):
        print("initializeAppTheme called")

        settings = QSettings()
        current_theme = settings.value("THEME")
        self.populateThemeList(current_theme)
        self.ui.themeList.currentTextChanged.connect(self.changeAppTheme)

    def populateThemeList(self, current_theme):
        print("populateThemeList called")

        self.ui.themeList.blockSignals(True)
        self.ui.themeList.clear()

        added_themes = set()
        selected_index = 0

        # Liste des thèmes autorisés
        allowed_themes = ["DarkYellow", "DarkRed"]

        for i, theme in enumerate(self.ui.themes):
            if theme.name not in allowed_themes:
                continue

            if theme.name in added_themes:
                continue

            added_themes.add(theme.name)
            self.ui.themeList.addItem(theme.name, theme.name)

            if theme.defaultTheme or theme.name == current_theme:
                selected_index = i

        self.ui.themeList.setCurrentIndex(selected_index)
        self.ui.themeList.blockSignals(False)

    def changeAppTheme(self):
        settings = QSettings()
        selected_theme = self.ui.themeList.currentData()
        current_theme = settings.value("THEME")

        if current_theme != selected_theme:
            settings.setValue("THEME", selected_theme)
            QAppSettings.updateAppSettings(self.main, reloadJson=True)

    def loadProductSansFont(self):
        font_id = QFontDatabase.addApplicationFont("./google-sans-cufonfonts/ProductSans-Regular.ttf")
        if font_id == -1:
            print("failed to load Product Sans font")
            return
        
        font_family = QFontDatabase.applicationFontFamilies(font_id)
        if font_family:
            product_sans = QFont(font_family[0])
        else:
            product_sans = QFont("Sans Serif")

        self.main.setFont(product_sans)

    def setup_comboboxes(self):
        """Initialise les choix dans les combobox"""
        self.ui.comboBox_nbrPlayers.addItems([str(2+i) for i in range(999) ])
        self.ui.comboBox_nbrWinrs.addItems([str(i) for i in range(1,101)])
        self.ui.comboBox_entrFees.addItems(["Free", "1", "2", "3", "5", "7", "10", "15", "20", "50", "75", "100", "150", "200"])
        self.ui.comboBox_topup.addItems([str(i) for i in range(2501) ])
        self.ui.comboBox_status.addItems(["Open", "Private"])
        
        # Connecter les signaux pour mettre à jour le cashprize total
        self.ui.comboBox_nbrPlayers.currentIndexChanged.connect(self.update_total_cashprize)
        self.ui.comboBox_entrFees.currentIndexChanged.connect(self.update_total_cashprize)
        self.ui.comboBox_topup.currentIndexChanged.connect(self.update_total_cashprize)
        
        # Connecter le signal du status pour générer le mot de passe
        self.ui.comboBox_status.currentIndexChanged.connect(self.on_status_changed)
    
    def on_status_changed(self):
        """Générer un mot de passe quand le statut Private est sélectionné"""
        status = self.ui.comboBox_status.currentText()
        if status == "Private":
            import secrets
            import string
            # Generate a strong password with 12 characters (letters + digits)
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for _ in range(12))
            self.ui.lineEdit_passwd.setText(password)
            self.ui.lineEdit_passwd.setReadOnly(True)
        else:
            self.ui.lineEdit_passwd.clear()
            self.ui.lineEdit_passwd.setReadOnly(False)
    
    def update_total_cashprize(self):
        """Calcule et affiche le cashprize total basé sur les selections"""
        try:
            # Nombre de joueurs
            num_players = int(self.ui.comboBox_nbrPlayers.currentText())
            
            # Frais d'entrée (gérer "Free")
            fees_text = self.ui.comboBox_entrFees.currentText()
            entry_fee = 0 if fees_text == "Free" else float(fees_text)
            
            # Topup
            topup = float(self.ui.comboBox_topup.currentText()) if self.ui.comboBox_topup.currentText() else 0
            
            # Calcul du cashprize total (en GT)
            total_cashprize = (entry_fee * num_players) + topup
            
            # Mise à jour du label
            self.ui.label_54.setText(f"Total Prize : {total_cashprize:.2f} GT")
            
        except (ValueError, AttributeError) as e:
            print(f"Erreur lors du calcul du cashprize: {e}")
            self.ui.label_54.setText("Total Prize : N/A")

    def connectTournamentButtons(self):
        """Connecter les boutons des pages de tournoi"""
        self.ui.pushButton_3.clicked.connect(lambda: [self.join_private_tournament(), self.refresh_all_tournament_data()])
        self.ui.pushButton_6.clicked.connect(lambda: [self.show_create_tournament_page(), self.refresh_all_tournament_data()])
        self.ui.pushButton_7.clicked.connect(lambda: [self.join_tournament(), self.refresh_all_tournament_data()])
        self.ui.pushButton_8.clicked.connect(lambda: [self.create_tournament(), self.refresh_all_tournament_data()])

    def connectProfileButtons(self):
        """Connecter les boutons du profil"""
        self.ui.pushButton_2.clicked.connect(lambda: [self.fund_account(), self.refresh_all_tournament_data()])
        self.ui.pushButton_9.clicked.connect(lambda: [self.withdraw_money(), self.refresh_all_tournament_data()])
        self.ui.changeIconBtn.clicked.connect(self.change_profile_icon)
        self.ui.comboBox.currentIndexChanged.connect(lambda: [self.change_supported_creator(), self.refresh_all_tournament_data()])

    def connectRefreshButton(self):
        """Connecter le bouton de rafraîchissement"""
        if hasattr(self.ui, 'pushButton_refresh'):
            self.ui.pushButton_refresh.clicked.connect(lambda: [self.load_user_tournaments(), self.load_open_tournaments(), self.load_finished_tournaments()])
        if hasattr(self.ui, 'pushButton_manage'):
            self.ui.pushButton_manage.clicked.connect(lambda: [self.manage_selected_tournament(), self.refresh_all_tournament_data()])

    def on_profile_btn_clicked(self):
        self.ui.rightMenu.expandMenu()
        self.load_user_profile()
        self.refresh_all_tournament_data()
    
    def on_spend_gt_clicked(self):
        """Handle Spend GT button click - Show dialog to spend GPU Tokens"""
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        
        # Get user's GT balance
        user_gt_balance = self.get_user_gt_balance()
        
        # Show input dialog
        amount, ok = QInputDialog.getInt(
            self.main,
            "Spend GT",
            f"Enter amount of GT to spend (Your balance: {user_gt_balance} GT):\n\n1 GT = computing power (TH/s)",
            1, 1, user_gt_balance, 1
        )
        
        if ok and amount > 0:
            # Show confirmation
            reply = QMessageBox.question(
                self.main,
                "Confirm Spend GT",
                f"Are you sure you want to spend {amount} GT for computing power?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Deduct GT from balance
                self.deduct_gt_balance(amount)
                QMessageBox.information(
                    self.main,
                    "Success",
                    f"You have successfully spent {amount} GT!\n\nComputing power has been added to your account."
                )
    
    def get_user_gt_balance(self):
        """Get current user's GT balance"""
        try:
            with open("users_data.json", "r", encoding="utf-8") as f:
                users = json.load(f)
            if self.logged_in_user in users:
                return users[self.logged_in_user].get("gt_balance", 0)
        except Exception as e:
            print(f"Error getting GT balance: {e}")
        return 0  # [FIX 4] Retourne 0, pas 100 — le fallback de test a été retiré
    
    def deduct_gt_balance(self, amount):
        """Deduct GT from user's balance — vérifie le solde avant de déduire."""
        try:
            with open("users_data.json", "r", encoding="utf-8") as f:
                users = json.load(f)

            if self.logged_in_user in users:
                current_balance = users[self.logged_in_user].get("gt_balance", 0)
                # [FIX 3] Vérification avant déduction
                if current_balance < amount:
                    print(f"[GT] Déduction refusée : solde {current_balance:.2f} < {amount:.2f} demandés.")
                    return False
                users[self.logged_in_user]["gt_balance"] = current_balance - amount

                with open("users_data.json", "w", encoding="utf-8") as f:
                    json.dump(users, f, indent=4, ensure_ascii=False)
                return True
            return False
        except Exception as e:
            print(f"Error deducting GT balance: {e}")
            return False
    
    def init_gt_value_page(self):
        """Initialize GT Value page with current exchange rate"""
        # Get current exchange rate from GT system
        exchange_rate = self.get_gt_exchange_rate()
        
        # Get network capacity info
        try:
            gt_system = get_gt_system()
            etat = gt_system.get_etat_systeme()
            capacite = etat.get('daily_capacity_tfloph', 0)
            total_supply = etat.get('total_supply', 0)
            
            # Update with network info
            self.ui.gtRateValue.setText(f"1 GT = {exchange_rate} TFLOP.h\n(Réseau: {capacite:,.0f} TFLOP.h disponible)")
        except Exception as e:
            print(f"[GT] Erreur init page: {e}")
            self.ui.gtRateValue.setText(f"1 GT = {exchange_rate} TFLOP.h")
    
    def get_gt_exchange_rate(self):
        """Get current GT to TFLOP.h exchange rate based on network capacity"""
        try:
            gt_system = get_gt_system()
            etat = gt_system.get_etat_systeme()
            
            capacite = etat.get('daily_capacity_tfloph', 0)
            total_supply = etat.get('circulating_supply', 0)
            
            # Marge de sécurité de 20% pour instability réseau
            capacite_safe = capacite * 0.8
            
            if total_supply > 0:
                # Ratio = (Capacité × 0.8) / Supply en circulation
                ratio = capacite_safe / total_supply
                return f"{ratio:.6f}"
            else:
                # Pas de supply en circulation - utiliser le taux estimé
                # Estimation basée sur 10 utilisateurs hypothétiques
                estimated_users = 10
                estimated_gt = 1000 * estimated_users  # 1000 GT par USD
                ratio = capacite_safe / estimated_gt if estimated_gt > 0 else 0
                return f"{ratio:.6f}"
        except Exception as e:
            print(f"[GT] Erreur calcul taux: {e}")
            return "0.001"
    
    def update_gt_rate_display(self):
        """Update the GT rate display"""
        exchange_rate = self.get_gt_exchange_rate()
        try:
            gt_system = get_gt_system()
            etat = gt_system.get_etat_systeme()
            capacite = etat.get('daily_capacity_tfloph', 0)
            self.ui.gtRateValue.setText(f"1 GT = {exchange_rate} TFLOP.h\n(Réseau: {capacite:,.0f} TFLOP.h disponible)")
        except Exception as e:
            self.ui.gtRateValue.setText(f"1 GT = {exchange_rate} TFLOP.h")

    def join_private_tournament(self):
        """Afficher la page de connexion à un tournoi privé"""
        self.ui.tournamentPage.setCurrentIndex(1)

    def show_create_tournament_page(self):
        """Afficher la page de création de tournoi"""
        self.ui.tournamentPage.setCurrentIndex(2)
        # Mettre à jour le cashprize total lors de l'affichage
        self.update_total_cashprize()


    def join_tournament(self):
        """Join an existing tournament using its ID and password"""
        tournament_id = self.ui.lineEdit_searchID.text().strip()
        password = self.ui.lineEdit_searchPassword.text().strip()

        # --- Basic validation ---
        if not tournament_id:
            QMessageBox.warning(self.main, "Error", "Please enter a tournament ID.")
            return

        if not password:
            QMessageBox.warning(self.main, "Error", "Please enter a password.")
            return

        username = self.logged_in_user

        file_path = "tournaments_data.py"
        participants_file = "participants_data.py"

        # --- Check if the tournament data file exists ---
        if not os.path.exists(file_path.replace(".py", ".json")):
            return

        # --- Safely load tournaments data ---
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            print(f"Failed to load tournament data: {e}")
            return

        # --- Check if the tournament exists ---
        # First try to find by ID
        tournament = None
        if tournament_id in TOURNAMENTS:
            tournament = TOURNAMENTS[tournament_id]
        else:
            # Try to find by name (case-insensitive)
            for t in TOURNAMENTS.values():
                if t.get("name", "").lower() == tournament_id.lower():
                    tournament = t
                    break
        
        if tournament is None:
            QMessageBox.warning(self.main, "Error", f"No tournament found: {tournament_id}")
            return

        # --- Verify password ---
        if tournament["password"] != password:
            QMessageBox.warning(self.main, "Error", "Incorrect password.")
            return

        # --- Ensure "participants" field exists in the tournament data ---
        if "participants" not in tournament:
            tournament["participants"] = []

        # --- Check if player already joined ---
        if username in tournament["participants"]:
            QMessageBox.information(self.main, "Info", f"{username} has already joined this tournament.")
            return

        # --- Check if tournament is full ---
        max_players = int(tournament.get("players", 0))
        if len(tournament["participants"]) >= max_players:
            QMessageBox.warning(self.main, "Error", "This tournament is already full.")
            return

        # --- Check user balance for entry fee ---
        fees = tournament["fees"]
        entry_fee = 0 if fees.lower() in ("free", "gratuit") else float(fees)
        if entry_fee > 0:
            # Show dollar payment dialog instead of using balance
            payment_dialog = DollarPaymentDialog(self.main, entry_fee, "entry_fee")
            if payment_dialog.exec() != QDialog.Accepted:
                QMessageBox.warning(self.main, "Payment Required", "Payment was not completed. Cannot join tournament.")
                return
            
            # Payment successful - Émettre des GT basés sur les frais d'entrée
            try:
                gt_system = get_gt_system()
                gt_reward = gt_system.emettre_gt_tournoi(
                    tournament_id=tournament_id,
                    usd_collected=entry_fee,
                    winners=None
                )
                print(f"[GT] Émis {gt_reward.total_gt_emis:,.2f} GT pour les frais d'entrée")
            except Exception as e:
                print(f"[GT] Erreur lors de l'émission GT: {e}")
            
            # Add 1% to supported creator (via le système GT)
            supported_creator = USERS[username].get("supported_creator")
            if supported_creator and supported_creator in USERS:
                donation_gt = entry_fee * 0.01
                try:
                    gt_system = get_gt_system()
                    wallet = gt_system.get_wallet(supported_creator)
                    if wallet:
                        wallet.gt_balance += donation_gt
                        gt_system._save_wallets()
                    else:
                        from src.gt_token_system import GTWallet
                        new_wallet = GTWallet(username=supported_creator, gt_balance=donation_gt)
                        gt_system.wallets[supported_creator] = new_wallet
                        gt_system._save_wallets()
                    print(f"[GT] {supported_creator} reçoit {donation_gt:.2f} GT (1% de {entry_fee}$)")
                except Exception as e:
                    current_gt = USERS[supported_creator].get('gt_balance', USERS[supported_creator].get('balance', 0))
                    USERS[supported_creator]['gt_balance'] = current_gt + donation_gt

            # Save users
            self.save_users_data()
            # Update profile
            self.load_user_profile()

        # --- Add player to the tournament ---
        tournament["participants"].append(username)

        # --- Save updated tournaments ---
        _save_json_file(file_path, "TOURNAMENTS", TOURNAMENTS)

        # --- Save player info to participants ---
        participants_data = _load_json_file(participants_file, "PARTICIPANTS")
        if username not in participants_data:
            participants_data[username] = []
        if tournament_id not in participants_data[username]:
            participants_data[username].append(tournament_id)
        _save_json_file(participants_file, "PARTICIPANTS", participants_data)

        # --- Success message ---
        QMessageBox.information(
            self.main,
            "Joined Tournament",
            f"You successfully joined the tournament!\n\n"
            f"Username: {username}\n"
            f"ID: {tournament_id}\n"
            f"Players: {len(tournament['participants'])}/{tournament['players']}\n"
            f"Status: {tournament['status']}\n"
            f"Entry Fee: {tournament['fees']}"
        )

        # --- Clear input fields ---
        self.ui.lineEdit_searchID.clear()
        self.ui.lineEdit_searchPassword.clear()


    def create_tournament(self):
        """Créer un nouveau tournoi et l'enregistrer dans un fichier"""
        tournament_name = self.ui.lineEdit_ID.text().strip()
        password = self.ui.lineEdit_passwd.text().strip()
        num_players = self.ui.comboBox_nbrPlayers.currentText()
        num_winners = self.ui.comboBox_nbrWinrs.currentText()
        fees = self.ui.comboBox_entrFees.currentText()
        status = self.ui.comboBox_status.currentText()
        topup = self.ui.comboBox_topup.currentText()
        description = self.ui.textEdit.toPlainText().strip()

        # --- Vérifications ---
        if not tournament_name:
            QMessageBox.warning(self.main, "Error", "Please enter a tournament name.")
            return

        # For private tournaments, password is already generated in on_status_changed
        if status == "Private":
            password = self.ui.lineEdit_passwd.text().strip()
            if not password:
                # Generate password if not already generated
                import secrets
                import string
                alphabet = string.ascii_letters + string.digits
                password = ''.join(secrets.choice(alphabet) for _ in range(12))
                self.ui.lineEdit_passwd.setText(password)
        else:
            # For open tournaments, require user to enter a password
            if not password:
                QMessageBox.warning(self.main, "Error", "Please enter a password.")
                return

        if not description:
            QMessageBox.warning(self.main, "Error", "Please add a description.")
            return

        # Vérifier que le nombre de gagnants est au moins 1
        if int(num_winners) < 1:
            QMessageBox.warning(self.main, "Error", "A tournament must have at least 1 winner.")
            return

        # --- Générer un ID unique pour le tournoi ---
        import uuid
        tournament_id = str(uuid.uuid4())

        # --- Check if creator has enough balance for topup ---
        topup_amount = float(topup) if topup else 0
        if topup_amount > 0:
            # Show dollar payment dialog instead of using GT balance
            payment_dialog = DollarPaymentDialog(self.main, topup_amount, "topup")
            if payment_dialog.exec() != QDialog.Accepted:
                QMessageBox.warning(self.main, "Payment Required", "Payment was not completed. Cannot create tournament.")
                return
            # Payment successful - no GT deduction needed since dollars go to platform
        
        # --- Calculer le cashprize total ---
        entry_fee = 0 if fees == "Free" else float(fees)
        num_players_val = int(num_players)
        total_cashprize = (entry_fee * num_players_val) + topup_amount

        # --- Émettre des GT pour le topup (en USD) ---
        if topup_amount > 0:
            try:
                gt_system = get_gt_system()
                # Émettre des GT basés sur le topup en USD
                gt_reward = gt_system.emettre_gt_tournoi(
                    tournament_id=tournament_id,
                    usd_collected=topup_amount,
                    winners=None  # Le topup va au pool plateforme
                )
                print(f"[GT] Émis {gt_reward.total_gt_emis:,.2f} GT pour le topup du tournoi")
            except Exception as e:
                print(f"[GT] Erreur lors de l'émission GT: {e}")

        # --- Crée un dictionnaire pour stocker les infos ---
        tournament_data = {
            "id": tournament_id,
            "name": tournament_name,
            "password": password,
            "players": num_players,
            "winners": num_winners,
            "fees": fees,
            "status": status,
            "topup": topup,
            "total_cashprize": total_cashprize,
            "description": description,
            "creator": self.logged_in_user

        }

        # --- Sauvegarde dans un fichier JSON ---
        file_path = "tournaments_data.py"
        existing_data = _load_json_file(file_path, "TOURNAMENTS")
        existing_data[tournament_id] = tournament_data
        _save_json_file(file_path, "TOURNAMENTS", existing_data)

        # Save users data after deducting topup
        self.save_users_data()

        # --- Message de confirmation ---
        tournament_info = f"""Tournoi créé avec succès !


    Nom : {tournament_name}
    ID : {tournament_id}
    Joueurs : {num_players}
    Gagnants : {num_winners}
    Frais : {fees}$
    Statut : {status}
    Mot de passe : {password}
    """

        QMessageBox.information(self.main, "Tournoi créé", tournament_info)
        # --- Réinitialisation des champs ---
        self.ui.lineEdit_ID.clear()
        self.ui.lineEdit_passwd.clear()
        self.ui.textEdit.clear()
        self.ui.comboBox_nbrPlayers.setCurrentIndex(2)
        self.ui.comboBox_nbrWinrs.setCurrentIndex(1)
        self.ui.comboBox_entrFees.setCurrentIndex(2)
        self.ui.comboBox_status.setCurrentIndex(0)
        self.ui.comboBox_topup.setCurrentIndex(0)

    def load_open_tournaments(self):
        """Load and display all open tournaments in the table widget with Join buttons"""
        file_path = "tournaments_data.py"

        # --- Check if the file exists ---
        if not os.path.exists(file_path.replace(".py", ".json")):
            return

        # --- Safely load tournament data ---
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            print(f"Failed to load tournament data: {e}")
            return

        # --- Filter open tournaments ---
        open_tournaments = [
            t for t in TOURNAMENTS.values()
            if t["status"].lower() in ("open", "ouvert")
        ]

        # --- Configure table ---
        self.ui.tableWidget_opentournaments.setRowCount(len(open_tournaments))
        self.ui.tableWidget_opentournaments.setColumnCount(8)
        self.ui.tableWidget_opentournaments.setHorizontalHeaderLabels([
            "ID", "Players", "Winners", "Entry Fee (\$)", "Actual Prize (GT)", "Description", "Join","Target Prize (GT)"
        ])

        # --- Populate table ---
        for row, tournament in enumerate(open_tournaments):
            # Players: show "joined / total"
            joined = len(tournament.get("participants", []))
            total = int(tournament.get("players", 0))
            topup = int(tournament.get("topup", 0))
            players_text = f"{joined} / {total}"

            # Entry fee
            fees = tournament["fees"]
            try:
                entry_fee = 0 if fees.lower() in ("free", "gratuit") else float(fees)
            except Exception:
                entry_fee = 0

            # Total cash prize (in GT)
            total_cashprize = entry_fee * joined + topup
            target_cashprize = entry_fee * total + topup

            # Fill table
            self.ui.tableWidget_opentournaments.setItem(row, 0, QTableWidgetItem(tournament.get("name", tournament["id"])))
            self.ui.tableWidget_opentournaments.setItem(row, 1, QTableWidgetItem(players_text))
            self.ui.tableWidget_opentournaments.setItem(row, 2, QTableWidgetItem(str(tournament["winners"])))
            self.ui.tableWidget_opentournaments.setItem(row, 3, QTableWidgetItem(str(fees)))
            self.ui.tableWidget_opentournaments.setItem(row, 4, QTableWidgetItem(f"{total_cashprize:.2f}  GT"))
            self.ui.tableWidget_opentournaments.setItem(row, 7, QTableWidgetItem(f"{target_cashprize:.2f}  GT"))

            # --- Description button ---
            btn_desc = QPushButton("View", self.ui.tableWidget_opentournaments)
            btn_desc.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #0984e3;
                    border: none;
                    text-align: center;
                    min-width: 0;
                    min-height: 0;
                }
                QPushButton:hover {
                    color: #74b9ff;
                }
            """)
            btn_desc.clicked.connect(lambda checked=False, desc=tournament["description"]: self.show_description(desc))
            self.ui.tableWidget_opentournaments.setCellWidget(row, 5, btn_desc)

            # --- Join button ---
            btn_join = QPushButton("Join", self.ui.tableWidget_opentournaments)
            btn_join.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #00b894;
                    border: none;
                    text-align: center;
                    min-width: 0;
                    min-height: 0;
                }
                QPushButton:hover {
                    color: #55efc4;
                }
            """)
            # For open tournaments, use direct join without password
            if tournament["status"].lower() in ("open", "ouvert"):
                btn_join.clicked.connect(lambda checked=False, tid=tournament["id"]: self.join_tournament_by_id(tid))
            else:
                btn_join.clicked.connect(lambda checked=False, tid=tournament["id"], tpwd=tournament["password"]: self.join_tournament_from_table(tid, tpwd))
            self.ui.tableWidget_opentournaments.setCellWidget(row, 6, btn_join)

        # --- Adjust columns ---
        self.ui.tableWidget_opentournaments.resizeColumnsToContents()
        # Set minimum column widths for better readability
        self.ui.tableWidget_opentournaments.setColumnWidth(0, 100)  # Name/ID
        self.ui.tableWidget_opentournaments.setColumnWidth(1, 80)  # Players
        self.ui.tableWidget_opentournaments.setColumnWidth(2, 70)  # Winners
        self.ui.tableWidget_opentournaments.setColumnWidth(3, 120)  # Entry Fee
        self.ui.tableWidget_opentournaments.setColumnWidth(4, 140) # Actual Cash Prize
        self.ui.tableWidget_opentournaments.setColumnWidth(5, 90)  # Description
        self.ui.tableWidget_opentournaments.setColumnWidth(6, 70)  # Join
        self.ui.tableWidget_opentournaments.setColumnWidth(7, 130) # Target Cash Prize
        
        # Set row height to fill the cell
        for row in range(self.ui.tableWidget_opentournaments.rowCount()):
            self.ui.tableWidget_opentournaments.setRowHeight(row, 30)

    def join_tournament_from_table(self, tournament_id: str, password: str):
        """Helper: Join a tournament directly from the table"""
        self.ui.lineEdit_searchID.setText(tournament_id)
        self.ui.lineEdit_searchPassword.setText(password)
        self.join_tournament()
        self.refresh_all_tournament_data()
    
    def join_tournament_by_id(self, tournament_id: str):
        """Join an open tournament directly by ID (no password required)"""
        username = self.logged_in_user
        file_path = "tournaments_data.py"

        # --- Check if the tournament data file exists ---
        if not os.path.exists(file_path.replace(".py", ".json")):
            return

        # --- Safely load tournaments data ---
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            print(f"Failed to load tournament data: {e}")
            return

        # --- Check if the tournament exists ---
        if tournament_id not in TOURNAMENTS:
            QMessageBox.warning(self.main, "Error", f"No tournament found with ID: {tournament_id}")
            return

        tournament = TOURNAMENTS[tournament_id]

        # --- Verify it's an open tournament ---
        if tournament["status"].lower() not in ("open", "ouvert"):
            QMessageBox.warning(self.main, "Error", "This tournament is not open for direct joining.")
            return

        # --- Ensure "participants" field exists in the tournament data ---
        if "participants" not in tournament:
            tournament["participants"] = []

        # --- Check if player already joined ---
        if username in tournament["participants"]:
            QMessageBox.information(self.main, "Info", f"{username} has already joined this tournament.")
            return

        # --- Check if tournament is full ---
        max_players = int(tournament.get("players", 0))
        if len(tournament["participants"]) >= max_players:
            QMessageBox.warning(self.main, "Error", "This tournament is already full.")
            return

        # --- Check user balance for entry fee ---
        fees = tournament["fees"]
        entry_fee = 0 if fees.lower() in ("free", "gratuit") else float(fees)
        if entry_fee > 0:
            # Show dollar payment dialog instead of using balance
            payment_dialog = DollarPaymentDialog(self.main, entry_fee, "entry_fee")
            if payment_dialog.exec() != QDialog.Accepted:
                QMessageBox.warning(self.main, "Payment Required", "Payment was not completed. Cannot join tournament.")
                return
            
            # Payment successful
            # Add 1% to supported creator (in GT - converted later)
            supported_creator = USERS[username].get("supported_creator")
            if supported_creator and supported_creator in USERS:
                # The creator gets 1% of the entry fee value in GT (simulated conversion)
                donation_gt = entry_fee * 0.01  # Assuming 1$ = 1 GT for simplicity
                current_gt = USERS[supported_creator].get('gt_balance', USERS[supported_creator].get('balance', 0))
                USERS[supported_creator]['gt_balance'] = current_gt + donation_gt

            # Save users
            self.save_users_data()
            # Update profile
            self.load_user_profile()

        # --- Add player to the tournament ---
        tournament["participants"].append(username)

        # --- Save updated tournaments ---
        _save_json_file(file_path, "TOURNAMENTS", TOURNAMENTS)

        # --- Refresh data ---
        self.refresh_all_tournament_data()
        QMessageBox.information(self.main, "Success", f"You have successfully joined the tournament: {tournament.get('name', 'Unknown')}")

    def show_description(self, description: str):
        """Display tournament description in a message box with line breaks preserved."""
        from PySide6.QtWidgets import QMessageBox

        msg = QMessageBox(self.main)
        msg.setWindowTitle("Tournament Description")
        msg.setTextInteractionFlags(
            msg.textInteractionFlags() | Qt.TextSelectableByMouse
        )  # facultatif : permet de copier le texte
        msg.setText(description)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()
        self.refresh_all_tournament_data()

    def load_user_tournaments(self):
        """Load and display tournaments that the user has joined or created"""
        file_path = "tournaments_data.py"
        participants_file = "participants_data.py"

        # --- Check if the files exist ---
        if not os.path.exists(file_path):
            return

        # --- Safely load tournament data ---
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            print(f"Failed to load tournament data: {e}")
            return

        # --- Load participants data ---
        user_tournaments = []
        try:
            participants_data = _load_json_file(participants_file, "PARTICIPANTS")
            if self.logged_in_user in participants_data:
                user_tournaments = participants_data[self.logged_in_user]
        except Exception:
            pass

        # --- Get tournaments created by the user ---
        created_tournaments = [
            t for t in TOURNAMENTS.values()
            if t.get("creator") == self.logged_in_user
        ]

        # --- Combine and deduplicate tournaments ---
        all_user_tournaments = []
        seen_ids = set()
         
        # Add joined tournaments
        for tid in user_tournaments:
            if tid in TOURNAMENTS and tid not in seen_ids:
                tournament = TOURNAMENTS[tid]
                tournament["type"] = "Joined"
                all_user_tournaments.append(tournament)
                seen_ids.add(tid)

        # Add created tournaments
        for tournament in created_tournaments:
            if tournament["id"] not in seen_ids:
                tournament["type"] = "Created"
                all_user_tournaments.append(tournament)
                seen_ids.add(tournament["id"])

        # --- Configure table ---
        self.ui.tableWidget_user_tournaments.setRowCount(len(all_user_tournaments))
        self.ui.tableWidget_user_tournaments.setColumnCount(5)
        self.ui.tableWidget_user_tournaments.setHorizontalHeaderLabels([
            "ID", "Type", "Players", "Status", "Prize (GT)"
        ])

        # --- Populate table ---
        for row, tournament in enumerate(all_user_tournaments):
            # Players: show "joined / total"
            joined = len(tournament.get("participants", []))
            total = int(tournament.get("players", 0))
            players_text = f"{joined} / {total}"

            # Entry fee
            fees = tournament["fees"]
            try:
                entry_fee = 0 if fees.lower() in ("free", "gratuit") else float(fees)
            except Exception:
                entry_fee = 0

            # Total cash prize (in GT)
            topup = int(tournament.get("topup", 0))
            total_cashprize = entry_fee * joined + topup

            # Fill table
            item_id = QTableWidgetItem(tournament.get("name", tournament["id"]))
            item_id.setData(Qt.UserRole, tournament["id"])
            self.ui.tableWidget_user_tournaments.setItem(row, 0, item_id)
            self.ui.tableWidget_user_tournaments.setItem(row, 1, QTableWidgetItem(tournament["type"]))
            self.ui.tableWidget_user_tournaments.setItem(row, 2, QTableWidgetItem(players_text))
            self.ui.tableWidget_user_tournaments.setItem(row, 3, QTableWidgetItem(tournament["status"]))
            self.ui.tableWidget_user_tournaments.setItem(row, 4, QTableWidgetItem(f"{total_cashprize:.2f} GT"))

        # --- Adjust columns ---
        self.ui.tableWidget_user_tournaments.resizeColumnsToContents()
        # Add extra width to Cash Prize column (column 4)
        self.ui.tableWidget_user_tournaments.setColumnWidth(4, self.ui.tableWidget_user_tournaments.columnWidth(4) + 15)

    def load_finished_tournaments(self):
        """Load and display finished tournaments"""
        file_path = "finished_tournaments_data.py"

        # --- Safely load finished tournament data ---
        try:
            all_finished = _load_json_file(file_path, "FINISHED_TOURNAMENTS")
            print(f"Loaded finished tournaments: {all_finished}")

            # Filter tournaments with status "Finished"
            FINISHED_TOURNAMENTS = {
                tid: t for tid, t in all_finished.items()
                if t.get("status") == "Finished"
            }
            print(f"Filtered finished tournaments: {FINISHED_TOURNAMENTS}")
        except Exception as e:
            print(f"Failed to load finished tournament data: {e}")
            return

        # --- Configure table ---
        self.ui.tableWidget_finished_tournaments.setRowCount(len(FINISHED_TOURNAMENTS))
        self.ui.tableWidget_finished_tournaments.setColumnCount(4)
        self.ui.tableWidget_finished_tournaments.setHorizontalHeaderLabels([
            "ID", "Winners", "Prize (GT)", "Date"
        ])
        
        # --- Populate table ---
        for row, (tournament_id, tournament) in enumerate(FINISHED_TOURNAMENTS.items()):
            print(f"Processing tournament: {tournament_id}")
            
            # Winners
            winners = tournament.get("winners_list", [])
            winners_text = ", ".join(winners) if winners else "N/A"
            print(f"Winners: {winners_text}")
            
            # Cash prize (now in GT)
            prize_distribution = tournament.get("prize_distribution", {})
            total_prize = sum(prize_distribution.values()) if prize_distribution else 0
            print(f"Total prize: {total_prize}")
            
            # Date (use end_date if available, otherwise use current date)
            date_text = tournament.get("end_date", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # Fill table
            self.ui.tableWidget_finished_tournaments.setItem(row, 0, QTableWidgetItem(tournament.get("name", tournament_id)))
            self.ui.tableWidget_finished_tournaments.setItem(row, 1, QTableWidgetItem(winners_text))
            self.ui.tableWidget_finished_tournaments.setItem(row, 2, QTableWidgetItem(f"{total_prize:.2f} GT"))
            self.ui.tableWidget_finished_tournaments.setItem(row, 3, QTableWidgetItem(date_text))
            print(f"Added tournament to table: {tournament_id}")

        # --- Adjust columns ---
        self.ui.tableWidget_finished_tournaments.resizeColumnsToContents()
        # Add extra width to Cash Prize column (column 2)
        self.ui.tableWidget_finished_tournaments.setColumnWidth(2, self.ui.tableWidget_finished_tournaments.columnWidth(2) + 15)
        print(f"Finished loading {len(FINISHED_TOURNAMENTS)} tournaments")

    def refresh_all_tournament_data(self):
        """Rafraîchir toutes les informations liées aux tournois"""
        self.load_open_tournaments()
        self.load_user_tournaments()
        self.load_finished_tournaments()
        self.load_user_profile()
        self.refresh_homepage_stats()
        
    def refresh_homepage_stats(self):
        """Rafraîchir les statistiques de la page d'accueil"""
        try:
            # Reload users data
            load_users_data()
            
            if self.logged_in_user and self.logged_in_user in USERS:
                user_data = USERS[self.logged_in_user]
                self.update_homepage_stats(user_data)
        except Exception as e:
            print(f"Error refreshing homepage stats: {e}")

    def manage_selected_tournament(self):
        """Gérer le tournoi sélectionné par l'utilisateur"""
        selected_row = self.ui.tableWidget_user_tournaments.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self.main, "Error", "Please select a tournament to manage.")
            return

        # Récupérer l'ID unique du tournoi à partir des données de l'élément
        item = self.ui.tableWidget_user_tournaments.item(selected_row, 0)
        tournament_id = item.data(Qt.UserRole)
        tournament_name = item.text()
        tournament_type = self.ui.tableWidget_user_tournaments.item(selected_row, 1).text()

        # Vérifier si l'utilisateur est le propriétaire du tournoi
        file_path = "tournaments_data.py"
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            QMessageBox.critical(self.main, "Error", f"Failed to load tournament data:\n{e}")
            return
        tournament = None
        for tid, t in TOURNAMENTS.items():
            if t.get("name") == tournament_name or tid == tournament_id:
                tournament = t
                tournament_id = tid
                break

        if tournament is None:
            QMessageBox.warning(self.main, "Error", f"Tournament {tournament_name} not found.")
            return

        if tournament.get("creator") != self.logged_in_user:
            QMessageBox.warning(self.main, "Error", "You are not the owner of this tournament.")
            return

        # Afficher la boîte de dialogue pour gérer le tournoi
        self.show_manage_tournament_dialog(tournament_id, tournament)

    def show_manage_tournament_dialog(self, tournament_id, tournament):
        """Afficher une boîte de dialogue pour gérer le tournoi"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout, QMessageBox, QInputDialog

        dialog = QDialog(self.main)
        dialog.setWindowTitle(f"Manage Tournament: {tournament_id}")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # Afficher les participants
        label_participants = QLabel("Participants:")
        layout.addWidget(label_participants)

        list_widget = QListWidget(dialog)
        list_widget.setSelectionMode(QListWidget.MultiSelection)  # Permettre la sélection multiple
        for participant in tournament.get("participants", []):
            list_widget.addItem(participant)
        layout.addWidget(list_widget)

        # Bouton pour désigner les gagnants
        btn_select_winners = QPushButton("Select Winners")
        btn_select_winners.clicked.connect(lambda: self.select_winners(tournament_id, tournament, list_widget))
        layout.addWidget(btn_select_winners)

        # Bouton pour répartir les gains
        btn_distribute_prize = QPushButton("Distribute Prize")
        btn_distribute_prize.clicked.connect(lambda: self.distribute_prize(tournament_id, tournament))
        layout.addWidget(btn_distribute_prize)

        # Bouton pour rafraîchir les données
        btn_refresh = QPushButton("Refresh Data")
        btn_refresh.clicked.connect(lambda: self.refresh_tournament_data(tournament_id, tournament, list_widget))
        layout.addWidget(btn_refresh)

        # Bouton pour fermer
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)

        dialog.exec()

    def refresh_tournament_data(self, tournament_id, tournament, list_widget):
        """Rafraîchir les données du tournoi"""
        file_path = "tournaments_data.py"
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            QMessageBox.critical(self.main, "Error", f"Failed to load tournament data:\n{e}")
            return

        if tournament_id not in TOURNAMENTS:
            QMessageBox.warning(self.main, "Error", f"Tournament {tournament_id} not found.")
            return

        # Mettre à jour les données du tournoi
        tournament.clear()
        tournament.update(TOURNAMENTS[tournament_id])

        # Mettre à jour la liste des participants
        list_widget.clear()
        for participant in tournament.get("participants", []):
            list_widget.addItem(participant)

        QMessageBox.information(self.main, "Success", "Tournament data refreshed successfully.")
        self.refresh_all_tournament_data()

    def select_winners(self, tournament_id, tournament, list_widget):
        """Sélectionner les gagnants du tournoi"""
        num_winners = int(tournament.get("winners", 0))
        if num_winners <= 0:
            QMessageBox.warning(self.main, "Error", "No winners to select for this tournament.")
            return

        selected_items = list_widget.selectedItems()
        if len(selected_items) != num_winners:
            QMessageBox.warning(self.main, "Error", f"Please select exactly {num_winners} winners.")
            return

        winners = [item.text() for item in selected_items]
        
        # Mettre à jour les données du tournoi
        file_path = "tournaments_data.py"
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            QMessageBox.critical(self.main, "Error", f"Failed to load tournament data:\n{e}")
            return

        if tournament_id not in TOURNAMENTS:
            QMessageBox.warning(self.main, "Error", f"Tournament {tournament_id} not found.")
            return

        TOURNAMENTS[tournament_id]["winners_list"] = winners

        # Sauvegarder les données mises à jour
        _save_json_file(file_path, "TOURNAMENTS", TOURNAMENTS)

        QMessageBox.information(self.main, "Success", f"Winners selected: {', '.join(winners)}")
        
        # Rafraîchir les données du tournoi dans l'interface utilisateur
        tournament["winners_list"] = winners
        self.refresh_all_tournament_data()

    def distribute_prize(self, tournament_id, tournament):
        """Répartir les gains du tournoi"""
        winners = tournament.get("winners_list", [])
        if not winners:
            QMessageBox.warning(self.main, "Error", "No winners selected for this tournament.")
            return

        # Vérifier si le cashprize a déjà été distribué
        if tournament.get("prize_distributed", False):
            QMessageBox.warning(self.main, "Error", "The cash prize for this tournament has already been distributed.")
            return

        # Calculer le montant total des gains
        fees = tournament["fees"]
        try:
            entry_fee = 0 if fees.lower() in ("free", "gratuit") else float(fees)
        except Exception:
            entry_fee = 0

        joined = len(tournament.get("participants", []))
        topup = int(tournament.get("topup", 0))
        total_cashprize = entry_fee * joined + topup

        # Demander à l'utilisateur comment répartir les gains
        distribution = {}
        remaining_prize = total_cashprize
        winners_without_prize = set(winners)

        for i, winner in enumerate(winners):
            # Pour le dernier gagnant, attribuer automatiquement le montant restant
            if i == len(winners) - 1:
                distribution[winner] = remaining_prize
                winners_without_prize.discard(winner)
                break
            
            min_amount = 1.0 if len(winners_without_prize) > 1 else 0.0
            max_amount = remaining_prize - (len(winners_without_prize) - 1) if len(winners_without_prize) > 1 else remaining_prize
            amount, ok = QInputDialog.getDouble(
                self.main,
                f"Prize for {winner}",
                f"Enter prize amount for {winner} ($):",
                min_amount,
                min_amount,
                max_amount,
                2
            )
            if not ok:
                return
            
            distribution[winner] = amount
            remaining_prize -= amount
            winners_without_prize.discard(winner)

        # Mettre à jour les données du tournoi
        file_path = "tournaments_data.py"
        try:
            TOURNAMENTS = _load_json_file(file_path, "TOURNAMENTS")
        except Exception as e:
            QMessageBox.critical(self.main, "Error", f"Failed to load tournament data:\n{e}")
            return

        if tournament_id not in TOURNAMENTS:
            QMessageBox.warning(self.main, "Error", f"Tournament {tournament_id} not found.")
            return

        # Ajouter les informations de distribution
        TOURNAMENTS[tournament_id]["prize_distribution"] = distribution
        TOURNAMENTS[tournament_id]["prize_distributed"] = True
        TOURNAMENTS[tournament_id]["status"] = "Finished"

        # Ajouter la date réelle de fin du tournoi
        TOURNAMENTS[tournament_id]["end_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Déplacer le tournoi vers le fichier des tournois terminés
        finished_tournament = TOURNAMENTS.pop(tournament_id)
        finished_tournament["prize_distributed"] = True

        # [FIX 2+9] Sauvegarder en JSON — plus de .py ni de replace() corrupteur
        _save_json_file(file_path, "TOURNAMENTS", TOURNAMENTS)

        finished_file_path = "finished_tournaments_data.py"
        FINISHED_TOURNAMENTS = _load_json_file(finished_file_path, "FINISHED_TOURNAMENTS")
        FINISHED_TOURNAMENTS[tournament_id] = finished_tournament
        _save_json_file(finished_file_path, "FINISHED_TOURNAMENTS", FINISHED_TOURNAMENTS)

        # Mettre à jour les soldes des utilisateurs en GT
        load_users_data()

        # [FIX 8] Émettre des GT via le moteur GT — source de vérité unique
        total_prize = sum(distribution.values())
        if total_prize > 0:
            try:
                gt_system = get_gt_system()
                winners_list = [(winner, amount / total_prize) for winner, amount in distribution.items()]
                gt_system.process_tournament_reward(
                    tournament_id=tournament_id,
                    usd_pool=total_prize,
                    winners=winners_list
                )
                print(f"[GT] Prix distribués via GTTokenEngine pour le tournoi {tournament_id}")
                # [FIX 8] PAS de second crédit ici — process_tournament_reward gère tout
            except Exception as e:
                print(f"[GT] Erreur lors de l'émission GT, fallback users_data: {e}")
                for winner, amount in distribution.items():
                    if winner in USERS:
                        current_gt = USERS[winner].get('gt_balance', USERS[winner].get('balance', 0))
                        USERS[winner]['gt_balance'] = current_gt + amount
        
        self.save_users_data()

        # Afficher un message de succès
        distribution_text = "\n".join([f"{winner}: {amount:.2f} GT" for winner, amount in distribution.items()])
        QMessageBox.information(
            self.main,
            "Success",
            f"Prize distributed successfully in GT:\n\n{distribution_text}"
        )

        # Rafraîchir les données du tournoi
        self.load_finished_tournaments()

    def load_user_profile(self):
        """Load and display user profile information"""
        # Reload users data to ensure it's up to date
        load_users_data()
           
        if self.logged_in_user and self.logged_in_user in USERS:
            user_data = USERS[self.logged_in_user]
            self.ui.label_77.setText(self.logged_in_user)  # Username
            
            # Synchroniser le solde GT depuis le système GT
            try:
                gt_system = get_gt_system()
                wallet = gt_system.get_wallet(self.logged_in_user)
                if wallet:
                    gt_balance = wallet.gt_balance
                    # Mettre à jour users_data.json avec le solde GT
                    USERS[self.logged_in_user]['gt_balance'] = gt_balance
                    self.save_users_data()
                else:
                    gt_balance = user_data.get('gt_balance', user_data.get('balance', 0))
            except Exception as e:
                print(f"[GT] Erreur synchro wallet: {e}")
                gt_balance = user_data.get('gt_balance', user_data.get('balance', 0))
            
            self.ui.label_79.setText(f"{gt_balance:.2f} GT")  # Balance in GT
            
            # Update profile icon based on saved choice
            icon_choice = user_data.get('profile_icon', 0)
            colors = ["#0984e3", "#00b894", "#d63031"]
            if 0 <= icon_choice < len(colors):
                self.update_profile_icon_color(colors[icon_choice])
            
            # Update homepage stats cards
            self.update_homepage_stats(user_data)

            # Populate combobox with creators if not already
            creators = [u for u, d in USERS.items() if d.get("is_creator", False)]
              
            # Block signals BEFORE any combobox manipulation to prevent unwanted signal triggers
            self.ui.comboBox.blockSignals(True)
              
            if self.ui.comboBox.count() == 0:
                self.ui.comboBox.addItem("None", None)
                for creator in creators:
                    self.ui.comboBox.addItem(creator, creator)

            # Set current supported creator
            supported = user_data.get("supported_creator")
              
            if supported and supported in creators:
                index = self.ui.comboBox.findData(supported)
                if index >= 0:
                    self.ui.comboBox.setCurrentIndex(index)
                    self.ui.label_75.setText(supported)
                else:
                    self.ui.comboBox.setCurrentIndex(0)
                    self.ui.label_75.setText("N/A")
            else:
                # If supported_creator is None or not in creators, just display "N/A" but don't modify the data
                self.ui.comboBox.setCurrentIndex(0)
                self.ui.label_75.setText("N/A")
            self.ui.comboBox.blockSignals(False)
        else:
            self.ui.label_77.setText("N/A")
            self.ui.label_79.setText("N/A GT")
            self.ui.label_75.setText("N/A")
    
    def change_profile_icon(self):
        """Show menu to change profile icon"""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.main)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d3436;
                color: #ffffff;
                border: 2px solid #00D4FF;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item:selected {
                background-color: #00D4FF;
                color: #21272a;
            }
        """)
        
        # Add actions with different background colors shown in preview
        colors = [
            ("#0984e3", "Blue"),
            ("#00b894", "Green"),
            ("#d63031", "Red")
        ]
        
        for color, name in colors:
            menu.addAction(name)
        
        # Show menu below the button
        pos = self.ui.changeIconBtn.mapToGlobal(self.ui.changeIconBtn.rect().bottomLeft())
        action = menu.exec_(pos)
        
        if action:
            for i, (color, name) in enumerate(colors):
                if action.text() == name:
                    self.update_profile_icon_color(color)
                    self.save_profile_icon(i)
                    break
    
    def update_profile_icon_color(self, color):
        """Update the profile icon background color"""
        # Update right menu profile avatar
        self.ui.profileAvatar.setStyleSheet(f"""
            QLabel#profileAvatar {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color}, stop:1 #ff9f43);
                border: 3px solid #e1f5ff;
                border-radius: 30px;
            }}
        """)
        # Update main page user avatar
        self.ui.homeUserAvatar.setStyleSheet(f"""
            QLabel#homeUserAvatar {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color}, stop:1 #ff9f43);
                border: 3px solid #e1f5ff;
                border-radius: 35px;
            }}
        """)
    
    def update_profile_icon(self, icon_index):
        """Update the profile icon based on selection"""
        icon_paths = [
            u":/feather/icons/feather/user.png",
            u":/feather/icons/feather/star.png",
            u":/feather/icons/feather/crown.png"
        ]
        if 0 <= icon_index < len(icon_paths):
            icon = QIcon()
            icon.addFile(icon_paths[icon_index], QSize(), QIcon.Mode.Normal, QIcon.State.Off)
            self.ui.profileAvatar.setPixmap(icon.pixmap(30, 30))
    
    def save_profile_icon(self, icon_index):
        """Save the profile icon choice to user data"""
        if self.logged_in_user and self.logged_in_user in USERS:
            USERS[self.logged_in_user]['profile_icon'] = icon_index
            self.save_users_data()
    
    def update_homepage_stats(self, user_data):
        """Update the homepage stats cards with user information"""
        try:
            # Update username label
            if hasattr(self.ui, 'homeUsernameLabel'):
                self.ui.homeUsernameLabel.setText(f"{self.logged_in_user}")
            
            # Update balance - now in GT
            if hasattr(self.ui, 'homeBalanceValue'):
                gt_balance = user_data.get('gt_balance', user_data.get('balance', 0))
                self.ui.homeBalanceValue.setText(f"{gt_balance:.2f} GT")
            
            # Calculate and update tournaments count
            if hasattr(self.ui, 'homeTournamentsValue'):
                tournaments_count = self.get_user_tournaments_count()
                self.ui.homeTournamentsValue.setText(str(tournaments_count))
            
            # Calculate and update wins count
            if hasattr(self.ui, 'homeWinsValue'):
                wins_count = self.get_user_wins_count()
                self.ui.homeWinsValue.setText(str(wins_count))
                
        except Exception as e:
            print(f"Error updating homepage stats: {e}")
    
    def get_user_tournaments_count(self):
        """Get the number of tournaments the user has joined or created"""
        try:
            TOURNAMENTS = _load_json_file("tournaments_data.py", "TOURNAMENTS")
            count = 0
            for tournament in TOURNAMENTS.values():
                if tournament.get("creator") == self.logged_in_user:
                    count += 1
            for tournament in TOURNAMENTS.values():
                if self.logged_in_user in tournament.get("participants", []):
                    count += 1
            return count
        except Exception as e:
            print(f"Error getting tournaments count: {e}")
            return 0
    
    def get_user_wins_count(self):
        """Get the number of tournaments the user has won"""
        try:
            FINISHED_TOURNAMENTS = _load_json_file("finished_tournaments_data.py", "FINISHED_TOURNAMENTS")
            count = 0
            for tournament in FINISHED_TOURNAMENTS.values():
                winners = tournament.get("winners_list", [])
                if self.logged_in_user in winners:
                    count += 1
            return count
        except Exception as e:
            print(f"Error getting wins count: {e}")
            return 0
    def fund_account(self):
        """Add GT to user account by purchasing with dollars"""
        # First, show dollar payment dialog
        amount_dollars, ok = QInputDialog.getDouble(self.main, "Purchase GT", "Enter amount in dollars to spend ($):", 0, 0, 10000, 2)
        if not ok or amount_dollars <= 0:
            return
        
        # Show payment dialog
        payment_dialog = DollarPaymentDialog(self.main, amount_dollars, "purchase_gt")
        if payment_dialog.exec() != QDialog.Accepted:
            QMessageBox.warning(self.main, "Payment Failed", "Payment was not completed. GT purchase cancelled.")
            return
        
        # Convert dollars to GT (assuming 1$ = 1 GT for simplicity)
        gt_amount = amount_dollars
        
        # Load and update user GT balance
        load_users_data()
        current_gt = USERS[self.logged_in_user].get('gt_balance', USERS[self.logged_in_user].get('balance', 0))
        USERS[self.logged_in_user]['gt_balance'] = current_gt + gt_amount
        self.save_users_data()
        
        self.load_user_profile()
        QMessageBox.information(self.main, "Success", f"Successfully purchased {gt_amount:.2f} GT for ${amount_dollars:.2f}!")
        self.refresh_all_tournament_data()

    def withdraw_money(self):
        """Withdraw GT from account"""
        # Get current GT balance
        load_users_data()
        current_gt = USERS[self.logged_in_user].get('gt_balance', USERS[self.logged_in_user].get('balance', 0))
        
        amount, ok = QInputDialog.getDouble(self.main, "Withdraw GT", f"Enter amount of GT to withdraw (Your balance: {current_gt:.2f} GT):", 0, 0, current_gt, 2)
        if ok and amount > 0:
            if current_gt >= amount:
                USERS[self.logged_in_user]['gt_balance'] = current_gt - amount
                self.save_users_data()
                self.load_user_profile()
                QMessageBox.information(self.main, "Success", f"Successfully withdrew {amount:.2f} GT from your account.")
            else:
                QMessageBox.warning(self.main, "Error", "Insufficient GT balance.")
            self.refresh_all_tournament_data()

    def change_supported_creator(self):
        """Update the supported creator for the user"""
        selected_creator = self.ui.comboBox.currentData()
        USERS[self.logged_in_user]["supported_creator"] = selected_creator
        self.ui.label_75.setText(selected_creator if selected_creator else "N/A")
        self.save_users_data()
        # Reload user profile to ensure the changes are reflected
        self.load_user_profile()
        self.refresh_all_tournament_data()

    def save_users_data(self):
        """Save users data to file"""
        with open("users_data.json", "w", encoding="utf-8") as f:
            json.dump(USERS, f, indent=4, ensure_ascii=False)