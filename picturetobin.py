import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFileDialog, QListWidget, QComboBox,
                             QMessageBox, QLineEdit, QColorDialog, QScrollArea, QSizePolicy,
                             QInputDialog)
from PyQt5.QtGui import QPixmap, QImage, QColor, QDragEnterEvent, QDropEvent, QDragMoveEvent, QDrag, QTransform
from PyQt5.QtCore import Qt, QMimeData, QByteArray, QDataStream, QIODevice, QSize
from PIL import Image  # 导入Pillow库
import struct

class ZoomableScrollArea(QScrollArea): # 自定义可缩放的 ScrollArea
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent # 保存父窗口 (ImageToBinConverter) 的引用
        self.setWidgetResizable(True)
        self.setMouseTracking(True) # 追踪鼠标，为了scroll area 捕获wheelEvent


    def wheelEvent(self, event):
        print("ZoomableScrollArea.wheelEvent triggered") # 调试信息
        if self.parent_window and self.parent_window.original_pixmap is not None:
            delta = event.angleDelta().y()
            print(f"  delta: {delta}") # 调试信息
            print(f"  zoom_scale before: {self.parent_window.zoom_scale}") # 调试信息
            zoom_changed = False
            if delta > 0: # 滚轮向前，放大
                if self.parent_window.zoom_scale < 2.0: #  更严格的放大限制: 2.0
                    self.parent_window.zoom_scale *= 1.1
                    zoom_changed = True
                    print("  Zoom in action taken") # 调试信息
                else:
                    print("  Zoom in limit reached") # 调试信息
            else:       # 滚轮向后，缩小
                if self.parent_window.zoom_scale > 0.1:
                    self.parent_window.zoom_scale /= 1.1
                    zoom_changed = True
                    print("  Zoom out action taken") # 调试信息
                else:
                    print("  Zoom out limit reached") # 调试信息
            print(f"  zoom_scale after: {self.parent_window.zoom_scale}") # 调试信息
            print(f"  zoom_changed: {zoom_changed}") # 调试信息

            if zoom_changed:
                self.parent_window.zoom_scale = max(0.1, min(self.parent_window.zoom_scale, 2.0)) # 限制最大缩放比例为 2.0
                self.parent_window._update_scaled_preview()
                event.accept()
                print("  event.accept() called, zoom performed") # 调试信息
                return # 提前返回，不再执行父类的 wheelEvent (滚动)
            else:
                print("  event.accept() NOT called, zoom NOT performed, should scroll") # 调试信息

        print("  Calling super().wheelEvent(event)") # 调试信息
        super().wheelEvent(event)


class ImageToBinConverter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片转BIN文件工具")
        self.setGeometry(100, 100, 800, 600)

        self.image_paths = []
        self.rgb_format_options = {
            "ARGB8888": "ARGB8888",
            "ARGB1555": "ARGB1555",
            "ARGB4444": "ARGB4444",
            "RGB666": "RGB666",
            "RGB565": "RGB565",
            "RGB444": "RGB444",
            "RGB888": "RGB888" #  新增 RGB888 格式
        }
        self.byte_order_options = {"小端模式": "<", "大端模式": ">"}  # '<' 小端, '>' 大端
        self.default_bg_color = QColor(255, 255, 255) # 默认白色背景
        self.bg_color = self.default_bg_color

        self.zoom_scale = 1.0  # 初始缩放比例
        self.original_pixmap = None # 保存原始 QPixmap，用于缩放

        self.initUI()

    def initUI(self):
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # 图片列表和操作按钮区域
        list_layout = QHBoxLayout()

        self.image_list_widget = QListWidget()
        self.image_list_widget.setDragDropMode(QListWidget.InternalMove) # 允许内部拖拽排序
        self.image_list_widget.setDefaultDropAction(Qt.MoveAction)
        self.image_list_widget.setSelectionMode(QListWidget.ExtendedSelection) # 允许选择多个项目
        self.image_list_widget.itemSelectionChanged.connect(self.update_preview) # 连接选择改变信号
        list_layout.addWidget(self.image_list_widget)

        button_layout = QVBoxLayout()
        self.open_image_button = QPushButton("打开图片")
        self.open_image_button.clicked.connect(self.open_image_file)
        button_layout.addWidget(self.open_image_button)

        self.open_folder_button = QPushButton("打开文件夹")
        self.open_folder_button.clicked.connect(self.open_image_folder)
        button_layout.addWidget(self.open_folder_button)

        self.clear_list_button = QPushButton("清空列表")
        self.clear_list_button.clicked.connect(self.clear_image_list)
        button_layout.addWidget(self.clear_list_button)

        list_layout.addLayout(button_layout)
        main_layout.addLayout(list_layout)

        # 预览区域和设置区域
        preview_setting_layout = QHBoxLayout()

        # 预览区域
        self.preview_scroll_area = ZoomableScrollArea(self) # 使用自定义的 ZoomableScrollArea, 并传入 self (ImageToBinConverter 实例)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_scroll_area.setWidget(self.preview_label) # widget仍然是 preview_label
        preview_setting_layout.addWidget(self.preview_scroll_area)

        # 设置区域
        setting_layout = QVBoxLayout()

        # RGB格式选择
        format_layout = QHBoxLayout()
        format_label = QLabel("RGB格式:")
        format_layout.addWidget(format_label)
        self.format_combo = QComboBox()
        self.format_combo.addItems(self.rgb_format_options.keys())
        format_layout.addWidget(self.format_combo)
        setting_layout.addLayout(format_layout)

        # 字节序选择
        byte_order_layout = QHBoxLayout()
        byte_order_label = QLabel("字节序:")
        byte_order_layout.addWidget(byte_order_label)
        self.byte_order_combo = QComboBox()
        self.byte_order_combo.addItems(self.byte_order_options.keys())
        byte_order_layout.addWidget(self.byte_order_combo)
        setting_layout.addLayout(byte_order_layout)

        # 背景色设置 (仅当ARGB转RGB时有效)
        bg_color_layout = QHBoxLayout()
        bg_color_label = QLabel("背景色(ARGB转RGB):")
        bg_color_layout.addWidget(bg_color_label)
        self.bg_color_edit = QLineEdit(self.default_bg_color.name()) # 初始显示默认颜色hex
        bg_color_layout.addWidget(self.bg_color_edit)
        self.bg_color_button = QPushButton("选择颜色")
        self.bg_color_button.clicked.connect(self.open_color_dialog)
        bg_color_layout.addWidget(self.bg_color_button)
        setting_layout.addLayout(bg_color_layout)


        preview_setting_layout.addLayout(setting_layout)
        main_layout.addLayout(preview_setting_layout)


        # 转换按钮和状态栏
        bottom_layout = QHBoxLayout()
        self.convert_button = QPushButton("转换为BIN文件")
        self.convert_button.clicked.connect(self.convert_to_bin)
        bottom_layout.addWidget(self.convert_button)
        main_layout.addLayout(bottom_layout)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("等待操作...")

        # 允许拖拽文件到窗口
        self.setAcceptDrops(True)

        # 初始预览空白
        self.update_preview()


    def open_image_file(self):
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Images (*.jpg *.jpeg *.bmp *.png)")
        file_dialog.setFileMode(QFileDialog.ExistingFiles) # 允许选择多个文件
        if file_dialog.exec_():
            filepaths = file_dialog.selectedFiles()
            for filepath in filepaths:
                if filepath not in self.image_paths: # 避免重复添加
                    self.image_paths.append(filepath)
                    self.image_list_widget.addItem(os.path.basename(filepath))
            if self.image_paths:
                self.update_preview()


    def open_image_folder(self):
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.Directory)
        if folder_dialog.exec_():
            folderpath = folder_dialog.selectedFiles()[0]
            for filename in os.listdir(folderpath):
                if filename.lower().endswith(('.jpg', '.jpeg', '.bmp', '.png')):
                    filepath = os.path.join(folderpath, filename)
                    if filepath not in self.image_paths: # 避免重复添加
                        self.image_paths.append(filepath)
                        self.image_list_widget.addItem(filename)
            if self.image_paths:
                self.update_preview()


    def clear_image_list(self):
        self.image_paths = []
        self.image_list_widget.clear()
        self.update_preview()
        self.status_bar.showMessage("图片列表已清空")


    def update_preview(self):
        if not self.image_paths:
            self.preview_label.clear()
            self.preview_label.setText("请添加图片进行预览")
            self.original_pixmap = None # 清空原始 pixmap
            return

        selected_items = self.image_list_widget.selectedItems()
        if selected_items:
            selected_index = self.image_list_widget.row(selected_items[0]) # 默认预览第一个选中的
        else:
            selected_index = 0 if self.image_paths else -1 # 预览第一个，或者-1如果列表为空

        if 0 <= selected_index < len(self.image_paths):
            image_path = self.image_paths[selected_index]
            try:
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    self.original_pixmap = pixmap # 保存原始 pixmap
                    self._update_scaled_preview()  # 调用缩放更新函数
                else:
                    self.preview_label.setText(f"无法加载图片: {os.path.basename(image_path)}")
                    self.original_pixmap = None
            except Exception as e:
                self.preview_label.setText(f"预览出错: {os.path.basename(image_path)}\n{str(e)}")
                self.original_pixmap = None
        else:
            self.preview_label.clear()
            self.preview_label.setText("请选择图片或添加图片进行预览")
            self.original_pixmap = None

    def _update_scaled_preview(self):
        if self.original_pixmap is None:
            return
        label_size = self.preview_label.size()
        target_size = label_size * self.zoom_scale # 计算目标尺寸

        # **尺寸限制** -  设置最大宽度和高度限制
        max_preview_size = 4096 #  您可以根据需要调整这个值
        target_width = min(target_size.width(), max_preview_size)
        target_height = min(target_size.height(), max_preview_size)
        limited_target_size = QSize(target_width, target_height) # 使用 QSize, 不需要 Qt. 前缀  **已修改**

        print("---- _update_scaled_preview ----") # 分隔线
        print(f"  Original Pixmap Size: {self.original_pixmap.width()} x {self.original_pixmap.height()}") # 原始Pixmap尺寸
        print(f"  Label Size: {label_size.width()} x {label_size.height()}") # QLabel尺寸
        print(f"  Zoom Scale: {self.zoom_scale}") # 缩放比例
        print(f"  Target Scaled Size (calculated): {target_size.width()} x {target_size.height()}") # 目标缩放尺寸 (原始计算值)
        print(f"  Target Scaled Size (limited): {limited_target_size.width()} x {limited_target_size.height()}") # 目标缩放尺寸 (限制后)


        try: # 尝试缩放，并捕获异常
            scaled_pixmap = self.original_pixmap.scaled(
                limited_target_size, # **使用限制后的尺寸**
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            print(f"  Scaled Pixmap Size: {scaled_pixmap.width()} x {scaled_pixmap.height()}") # 缩放后的Pixmap 尺寸
            self.preview_label.setPixmap(scaled_pixmap)
            print("  Pixmap updated successfully") # 更新成功信息
        except Exception as e:
            print(f"  Error in scaled(): {e}") # 缩放失败错误信息
            import traceback
            traceback.print_exc() # 打印完整错误堆栈



    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_preview() # 窗口大小改变时更新预览尺寸


    def open_color_dialog(self):
        color_dialog = QColorDialog.getColor(self.bg_color, self, "选择背景颜色")
        if color_dialog.isValid():
            self.bg_color = color_dialog
            self.bg_color_edit.setText(self.bg_color.name())


    def convert_to_bin(self):
        if not self.image_paths:
            QMessageBox.warning(self, "警告", "请先添加图片到列表!")
            return

        bin_file_path, _ = QFileDialog.getSaveFileName(self, "保存BIN文件", "", "BIN Files (*.bin)")
        if not bin_file_path:
            return

        selected_format_name = self.format_combo.currentText()
        selected_format = self.rgb_format_options[selected_format_name]
        selected_byte_order = self.byte_order_options[self.byte_order_combo.currentText()]
        bg_color_hex = self.bg_color_edit.text()

        try:
            bg_color = QColor(bg_color_hex)
            if not bg_color.isValid():
                QMessageBox.warning(self, "背景色错误", "背景颜色格式不正确!")
                return
            bg_rgb = (bg_color.red(), bg_color.green(), bg_color.blue())
        except:
            QMessageBox.warning(self, "背景色错误", "背景颜色格式不正确!")
            return


        try:
            with open(bin_file_path, 'wb') as bin_file:
                for image_path in self.image_paths:
                    self.status_bar.showMessage(f"正在处理: {os.path.basename(image_path)} ...")
                    QApplication.processEvents() # 立即更新状态栏

                    img = Image.open(image_path)
                    img = img.convert('RGBA') # 统一转换为RGBA方便处理透明和各种格式
                    width, height = img.size
                    img_data = list(img.getdata())

                    bin_data = bytearray()

                    for pixel in img_data:
                        r, g, b, a = pixel # RGBA

                        if selected_format_name.startswith("ARGB") and a < 255: # 如果是ARGB格式且像素透明，应用背景色
                            r_bg, g_bg, b_bg = bg_rgb
                            r = int((1 - a / 255) * r_bg + (a / 255) * r)
                            g = int((1 - a / 255) * g_bg + (a / 255) * g)
                            b = int((1 - a / 255) * b_bg + (a / 255) * b)

                        if selected_format == "ARGB8888":
                            bin_data.extend(struct.pack(f"{selected_byte_order}I", (a << 24) | (r << 16) | (g << 8) | b))
                        elif selected_format == "ARGB1555":
                            color_555 = ((a & 0x80) << 8) | ((b & 0xF8) << 7) | ((g & 0xF8) << 2) | (r >> 3)
                            bin_data.extend(struct.pack(f"{selected_byte_order}H", color_555))
                        elif selected_format == "ARGB4444":
                            color_4444 = ((a & 0xF0) << 8) | ((b & 0xF0) << 4) | (g & 0xF0)  | (r >> 4)
                            bin_data.extend(struct.pack(f"{selected_byte_order}H", color_4444))
                        elif selected_format == "RGB666": # 实际存储可能需要考虑填充到字节
                            color_666 = ((r & 0x3F) << 12) | ((g & 0x3F) << 6) | (b & 0x3F)
                            bin_data.extend(struct.pack(f"{selected_byte_order}H", color_666)) # 存储为2字节，可能需要调整
                        elif selected_format == "RGB565":
                            color_565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                            bin_data.extend(struct.pack(f"{selected_byte_order}H", color_565))
                        elif selected_format == "RGB444":
                            color_444 = ((r & 0xF0) << 4) | (g & 0xF0) | (b >> 4) # 低4位舍弃
                            bin_data.extend(struct.pack(f"{selected_byte_order}H", color_444)) #  存储为2字节，可能需要调整
                        elif selected_format == "RGB888": # 新增 RGB888
                            bin_data.extend(struct.pack(f"{selected_byte_order}BBB", r, g, b))


                    # 4KB 对齐和间隔
                    current_size = len(bin_data)
                    padding_needed = (4096 - (current_size % 4096)) % 4096 # 计算需要多少padding达到4K
                    bin_data.extend(b'\x00' * padding_needed) # 填充0对齐4K
                    bin_file.write(bin_data)
                    bin_file.write(b'\x00' * 4096) # 4KB间隔

                self.status_bar.showMessage(f"BIN文件已保存到: {bin_file_path}")
                QMessageBox.information(self, "完成", f"BIN文件已保存到: {bin_file_path}")

        except Exception as e:
            self.status_bar.showMessage(f"转换出错: {str(e)}")
            QMessageBox.critical(self, "错误", f"转换BIN文件出错: {str(e)}")


    #  ----  拖拽文件支持  ----
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent):
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith(('.jpg', '.jpeg', '.bmp', '.png')):
                if filepath not in self.image_paths:
                    self.image_paths.append(filepath)
                    self.image_list_widget.addItem(os.path.basename(filepath))
        if self.image_paths:
            self.update_preview()
        event.acceptProposedAction()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    converter = ImageToBinConverter()
    converter.show()
    sys.exit(app.exec_())
