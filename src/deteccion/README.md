# Detección de medicamentos (YOLO) — pendiente

Espacio reservado para el modelo de visión (ultralytics / YOLO) que identifica el
medicamento en la foto antes del OCR. La columna `inventario_carro.confianza_deteccion`
ya existe para guardar su confianza. Al integrarlo, la vista `app/vistas/ocr.py`
puede preseleccionar el medicamento detectado en el formulario de registro.
