# -*- coding: utf-8 -*-

import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict

from humanize import naturalsize, naturaltime
from PyQt5.QtCore import QFileInfo, QSize, Qt, pyqtSlot
from PyQt5.QtGui import QColor, QIcon, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QAction, QFileIconProvider, QToolBar

from gridsync import config_dir, resource
from gridsync.gui.pixmap import CompositePixmap
from gridsync.magic_folder import MagicFolderStatus
from gridsync.preferences import get_preference
from gridsync.util import humanized_list


class Model(QStandardItemModel):
    def __init__(self, view):
        super().__init__(0, 5)
        self.view = view
        self.gui = self.view.gui
        self.gateway = self.view.gateway
        self.monitor = self.gateway.monitor
        self.status_dict = {}
        self.members_dict = {}
        self.grid_status = ""
        self.available_space = 0
        self._magic_folder_errors = defaultdict(dict)
        self.setHeaderData(0, Qt.Horizontal, "Name")
        self.setHeaderData(1, Qt.Horizontal, "Status")
        self.setHeaderData(2, Qt.Horizontal, "Last modified")
        self.setHeaderData(3, Qt.Horizontal, "Size")
        self.setHeaderData(4, Qt.Horizontal, "")

        self.icon_blank = QIcon()
        self.icon_up_to_date = QIcon(resource("checkmark.png"))
        self.icon_user = QIcon(resource("user.png"))
        self.icon_folder = QFileIconProvider().icon(QFileInfo(config_dir))
        composite_pixmap = CompositePixmap(
            self.icon_folder.pixmap(256, 256), overlay=None, grayout=True
        )
        self.icon_folder_gray = QIcon(composite_pixmap)
        self.icon_cloud = QIcon(resource("cloud-icon.png"))
        self.icon_action = QIcon(resource("dots-horizontal-triple.png"))
        self.icon_error = QIcon(resource("alert-circle-red.png"))

        self.monitor.connected.connect(self.on_connected)
        self.monitor.disconnected.connect(self.on_disconnected)
        self.monitor.nodes_updated.connect(self.on_nodes_updated)
        self.monitor.space_updated.connect(self.on_space_updated)
        self.monitor.check_finished.connect(self.update_natural_times)

        self.mf_monitor = self.gateway.magic_folder.monitor
        self.mf_monitor.folder_added.connect(
            # Make the "Status" column blank until a sync completes
            lambda x: self.add_folder(x, None)
        )
        self.mf_monitor.folder_removed.connect(self.on_folder_removed)
        self.mf_monitor.folder_mtime_updated.connect(self.set_mtime)
        self.mf_monitor.folder_size_updated.connect(self.set_size)
        self.mf_monitor.backup_added.connect(self.add_remote_folder)
        self.mf_monitor.folder_state_changed.connect(self.set_status)
        self.mf_monitor.error_occurred.connect(self.on_error_occurred)
        self.mf_monitor.files_updated.connect(self.on_files_updated)
        self.mf_monitor.sync_progress_updated.connect(
            self.set_transfer_progress
        )

    @pyqtSlot(str, str, int)
    def on_error_occurred(
        self, folder_name: str, summary: str, timestamp: int
    ) -> None:
        self._magic_folder_errors[folder_name][summary] = timestamp

    def on_space_updated(self, size):
        self.available_space = size

    @pyqtSlot(int, int)
    def on_nodes_updated(self, num_connected, num_happy):
        if num_connected < num_happy:
            self.grid_status = "Connecting ({}/{} nodes){}".format(
                num_connected,
                num_happy,
                (" via Tor..." if self.gateway.use_tor else "..."),
            )
        elif num_connected >= num_happy:
            self.grid_status = "Connected to {} {}{} {} available".format(
                num_connected,
                "storage " + ("node" if num_connected == 1 else "nodes"),
                (" via Tor;" if self.gateway.use_tor else ";"),
                naturalsize(self.available_space),
            )
        self.gui.main_window.set_current_grid_status()  # TODO: Use pyqtSignal?

    @pyqtSlot()
    def on_connected(self):
        if get_preference("notifications", "connection") == "true":
            self.gui.show_message(
                self.gateway.name, "Connected to {}".format(self.gateway.name)
            )

    @pyqtSlot()
    def on_disconnected(self):
        if get_preference("notifications", "connection") == "true":
            self.gui.show_message(
                self.gateway.name,
                "Disconnected from {}".format(self.gateway.name),
            )

    @pyqtSlot(str, list, str, str)
    def on_updated_files(self, folder_name, files_list, action, author):
        if get_preference("notifications", "folder") != "false":
            self.gui.show_message(
                folder_name + " folder updated",
                "{} {}".format(
                    author + " " + action if author else action.capitalize(),
                    humanized_list(files_list),
                ),
            )

    @pyqtSlot(str, list)
    def on_files_updated(self, folder_name: str, files: list) -> None:
        if get_preference("notifications", "folder") != "false":
            self.gui.show_message(
                f"{folder_name} folder updated",
                f"Updated {humanized_list(files)}",
            )

    def data(self, index, role):
        value = super().data(index, role)
        if role == Qt.SizeHintRole:
            return QSize(0, 30)
        return value

    def add_folder(self, path, status_data=0):
        basename = os.path.basename(os.path.normpath(path))
        if self.findItems(basename):
            logging.warning(
                "Tried to add a folder (%s) that already exists", basename
            )
            return
        composite_pixmap = CompositePixmap(self.icon_folder.pixmap(256, 256))
        name = QStandardItem(QIcon(composite_pixmap), basename)
        name.setToolTip(path)
        status = QStandardItem()
        mtime = QStandardItem()
        size = QStandardItem()
        action = QStandardItem()
        self.appendRow([name, status, mtime, size, action])
        action_bar = QToolBar()
        action_bar.setIconSize(QSize(16, 16))
        if sys.platform == "darwin":
            # See: https://bugreports.qt.io/browse/QTBUG-12717
            action_bar.setStyleSheet(
                "background-color: {0}; border: 0px {0}".format(
                    self.view.palette().base().color().name()
                )
            )
        action_bar_action = QAction(self.icon_action, "Action...", self)
        action_bar_action.setStatusTip("Action...")
        action_bar_action.triggered.connect(self.view.on_right_click)
        action_bar.addAction(action_bar_action)
        self.view.setIndexWidget(action.index(), action_bar)
        self.view.hide_drop_label()
        self.set_status(basename, status_data)

    def remove_folder(self, folder_name):
        self.gui.systray.remove_operation((self.gateway, folder_name))
        items = self.findItems(folder_name)
        if items:
            self.removeRow(items[0].row())

    def update_folder_icon(self, folder_name, overlay_file=None):
        items = self.findItems(folder_name)
        if items:
            folder_path = self.gateway.magic_folder.get_directory(folder_name)
            if folder_path:
                folder_icon = QFileIconProvider().icon(QFileInfo(folder_path))
            else:
                folder_icon = self.icon_folder_gray
            folder_pixmap = folder_icon.pixmap(256, 256)
            if overlay_file:
                pixmap = CompositePixmap(folder_pixmap, resource(overlay_file))
            else:
                pixmap = CompositePixmap(folder_pixmap)
            items[0].setIcon(QIcon(pixmap))

    def set_status_private(self, folder_name):
        self.update_folder_icon(folder_name)
        items = self.findItems(folder_name)
        if items:
            items[0].setToolTip(
                "{}\n\nThis folder is private; only you can view and\nmodify "
                "its contents.".format(
                    self.gateway.magic_folder.get_directory(folder_name)
                    or folder_name + " (Stored remotely)"
                )
            )

    def set_status_shared(self, folder_name):
        self.update_folder_icon(folder_name, "laptop.png")
        items = self.findItems(folder_name)
        if items:
            items[0].setToolTip(
                "{}\n\nAt least one other device can view and modify\n"
                "this folder's contents.".format(
                    self.gateway.magic_folder.get_directory(folder_name)
                    or folder_name + " (Stored remotely)"
                )
            )

    def update_overlay(self, folder_name):
        members = self.members_dict.get(folder_name)
        if members and len(members) > 1:
            self.set_status_shared(folder_name)
        else:
            self.set_status_private(folder_name)

    @pyqtSlot(str, list)
    def on_members_updated(self, folder, members):
        self.members_dict[folder] = members
        self.update_overlay(folder)

    @staticmethod
    def _errors_to_str(errors: Dict[str, int]) -> str:
        lines = []
        for s, t in sorted(errors.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"{s} ({datetime.fromtimestamp(t)})")
        return "\n".join(lines)

    def is_folder_syncing(self) -> bool:
        for row in range(self.rowCount()):
            if self.item(row, 1).data(Qt.UserRole) == MagicFolderStatus.SYNCING:
                return True
        return False

    @pyqtSlot(str, object)
    def set_status(self, name, status):
        items = self.findItems(name)
        if not items:
            return
        item = self.item(items[0].row(), 1)
        if status == MagicFolderStatus.LOADING:
            item.setIcon(self.icon_blank)
            item.setText("Loading...")
        elif status == MagicFolderStatus.WAITING:
            item.setIcon(self.icon_blank)
            item.setText("Waiting to scan...")
        elif status == MagicFolderStatus.SYNCING:
            item.setIcon(self.icon_blank)
            item.setText("Syncing")
            item.setToolTip(
                "This folder is syncing. New files are being uploaded or "
                "downloaded."
            )
        elif status == MagicFolderStatus.UP_TO_DATE:
            item.setIcon(self.icon_up_to_date)
            item.setText("Up to date")
            item.setToolTip(
                "This folder is up to date. The contents of this folder on\n"
                "your computer matches the contents of the folder on the\n"
                '"{}" grid.'.format(self.gateway.name)
            )
            self.update_overlay(name)
            self.unfade_row(name)
        elif status == MagicFolderStatus.STORED_REMOTELY:
            item.setIcon(self.icon_cloud)
            item.setText("Stored remotely")
            item.setToolTip(
                'This folder is stored remotely on the "{}" grid.\n'
                'Right-click and select "Download" to sync it with your '
                "local computer.".format(self.gateway.name)
            )
        elif status == MagicFolderStatus.ERROR:
            errors = self._magic_folder_errors[name]
            if errors:
                item.setIcon(self.icon_error)
                item.setText("Error syncing folder")
                item.setToolTip(self._errors_to_str(errors))
        if status == MagicFolderStatus.SYNCING:
            self.gui.systray.add_operation((self.gateway, name))
            self.gui.systray.update()
        else:
            self.gui.systray.remove_operation((self.gateway, name))
        item.setData(status, Qt.UserRole)
        self.status_dict[name] = status

    @pyqtSlot(str, object, object)
    def set_transfer_progress(self, folder_name, transferred, total):
        items = self.findItems(folder_name)
        if not items:
            return
        percent_done = int(transferred / total * 100)
        if not percent_done:
            # Magic-folder's periodic "full scan" (which occurs every 10
            # minutes) temporarily adds *all* known files to the queue
            # exposed by the "status" API for a very brief period (seemingly
            # for only a second or two). Because of this -- and since we rely
            # on the magic-folder "status" API to tell us information about
            # current and pending transfers to calculate total progress --
            # existing "syncing" operations will briefly display a progress
            # of "0%" during this time (since the number of bytes to be
            # transferred briefly becomes equal to the total size of the
            # entire folder -- even though those transfers do not occur and
            # vanish from the queue as soon as the the "full scan" is
            # completed). To compensate for this strange (and rare) event --
            # and because it's probably jarring to the end-user to see
            # progress dip down to "0%" for a brief moment before returning to
            # normal -- we ignore any updates to "0" here (on the assumption
            # that it's better to have a couple of seconds of no progress
            # updates than a progress update which is wrong or misleading).
            return
        item = self.item(items[0].row(), 1)
        item.setText("Syncing ({}%)".format(percent_done))

    def fade_row(self, folder_name, overlay_file=None):
        try:
            folder_item = self.findItems(folder_name)[0]
        except IndexError:
            return
        if overlay_file:
            folder_pixmap = self.icon_folder_gray.pixmap(256, 256)
            pixmap = CompositePixmap(folder_pixmap, resource(overlay_file))
            folder_item.setIcon(QIcon(pixmap))
        else:
            folder_item.setIcon(self.icon_folder_gray)
        row = folder_item.row()
        for i in range(4):
            item = self.item(row, i)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            item.setForeground(QColor("gray"))

    def unfade_row(self, folder_name):
        folder_item = self.findItems(folder_name)[0]
        row = folder_item.row()
        for i in range(4):
            item = self.item(row, i)
            font = item.font()
            font.setItalic(False)
            item.setFont(font)
            item.setForeground(self.view.palette().text())

    @pyqtSlot(str, int)
    def set_mtime(self, name, mtime):
        if not mtime:
            return
        items = self.findItems(name)
        if items:
            item = self.item(items[0].row(), 2)
            item.setData(mtime, Qt.UserRole)
            item.setText(
                naturaltime(datetime.now() - datetime.fromtimestamp(mtime))
            )
            item.setToolTip("Last modified: {}".format(time.ctime(mtime)))

    @pyqtSlot(str, object)
    def set_size(self, name, size):
        items = self.findItems(name)
        if items:
            item = self.item(items[0].row(), 3)
            item.setText(naturalsize(size))
            item.setData(size, Qt.UserRole)

    @pyqtSlot()
    def update_natural_times(self):
        for i in range(self.rowCount()):
            item = self.item(i, 2)
            data = item.data(Qt.UserRole)
            if data:
                item.setText(
                    naturaltime(datetime.now() - datetime.fromtimestamp(data))
                )

    @pyqtSlot(str)
    @pyqtSlot(str, str)
    def add_remote_folder(self, folder_name, overlay_file=None):
        self.add_folder(folder_name, MagicFolderStatus.STORED_REMOTELY)
        self.fade_row(folder_name, overlay_file)

    @pyqtSlot(str)
    def on_folder_removed(self, folder_name: str):
        self.set_status(folder_name, MagicFolderStatus.STORED_REMOTELY)
        self.fade_row(folder_name)
