"""Datos maestros de referencia usados por la inicialización y el generador de histórico.
Costos en COP: valores referenciales para la simulación, no precios oficiales."""

SERVICIOS = ["Urgencias", "UCI Adultos", "UCI Pediátrica", "Hospitalización", "Cirugía", "Pediatría"]

# codigo, servicio, ubicación
CARROS = [
    ("CP-URG-01", "Urgencias", "Sala de reanimación"),
    ("CP-URG-02", "Urgencias", "Observación adultos"),
    ("CP-URG-03", "Urgencias", "Triage"),
    ("CP-UCI-01", "UCI Adultos", "Módulo A"),
    ("CP-UCI-02", "UCI Adultos", "Módulo B"),
    ("CP-UCIP-01", "UCI Pediátrica", "Módulo único"),
    ("CP-HOS-01", "Hospitalización", "Piso 3"),
    ("CP-HOS-02", "Hospitalización", "Piso 4"),
    ("CP-HOS-03", "Hospitalización", "Piso 5"),
    ("CP-CIR-01", "Cirugía", "Recuperación"),
    ("CP-CIR-02", "Cirugía", "Quirófanos"),
    ("CP-PED-01", "Pediatría", "Piso 2"),
]

# nombre, principio activo, criticidad, min, max, costo, tasa relativa de uso por evento
MEDICAMENTOS = [
    ("Adrenalina 1mg/ml", "Epinefrina", "ALTA", 6, 10, 3500, 3.5),
    ("Atropina 1mg/ml", "Atropina", "ALTA", 3, 6, 2800, 1.2),
    ("Amiodarona 150mg/3ml", "Amiodarona", "ALTA", 3, 6, 9800, 1.0),
    ("Bicarbonato de Sodio 1mEq/ml", "Bicarbonato de sodio", "MEDIA", 2, 4, 6500, 0.6),
    ("Sulfato de Magnesio 20%", "Sulfato de magnesio", "MEDIA", 2, 4, 3900, 0.3),
    ("Gluconato de Calcio 10%", "Gluconato de calcio", "MEDIA", 2, 4, 4200, 0.3),
    ("Dextrosa 50%", "Dextrosa", "MEDIA", 2, 4, 5200, 0.4),
    ("Lidocaína 2% sin epinefrina", "Lidocaína", "ALTA", 2, 4, 3100, 0.4),
    ("Adenosina 6mg/2ml", "Adenosina", "ALTA", 3, 6, 18500, 0.3),
    ("Naloxona 0.4mg/ml", "Naloxona", "MEDIA", 2, 4, 21000, 0.15),
    ("Flumazenil 0.5mg/5ml", "Flumazenil", "BAJA", 1, 2, 38000, 0.05),
    ("Dopamina 200mg/5ml", "Dopamina", "ALTA", 2, 4, 7600, 0.5),
    ("Norepinefrina 4mg/4ml", "Norepinefrina", "ALTA", 2, 4, 14500, 0.6),
    ("Furosemida 20mg/2ml", "Furosemida", "BAJA", 2, 4, 1900, 0.3),
    ("Hidrocortisona 100mg", "Hidrocortisona", "MEDIA", 2, 4, 11200, 0.3),
    ("Solución Salina 0.9% 500ml", "Cloruro de sodio", "ALTA", 4, 6, 4800, 1.5),
    ("Lactato de Ringer 500ml", "Lactato de Ringer", "MEDIA", 2, 4, 5100, 0.7),
    ("Midazolam 5mg/ml", "Midazolam", "MEDIA", 2, 4, 6900, 0.4),
]

# probabilidad diaria de código azul por servicio (simulación)
TASA_CODIGO_AZUL = {"Urgencias": 0.22, "UCI Adultos": 0.18, "UCI Pediátrica": 0.07,
                    "Hospitalización": 0.05, "Cirugía": 0.06, "Pediatría": 0.03}

USUARIOS_DEMO = [
    ("Administrador General", "admin@hospital.com", "ADMIN"),
    ("Dra. Laura Médica", "medico@hospital.com", "MEDICO"),
    ("Carlos Enfermero", "enfermero@hospital.com", "ENFERMERO"),
    ("Sofía Regente", "regente@hospital.com", "REGENTE_FARMACIA"),
    ("Roberto Auditor", "auditor@hospital.com", "AUDITOR"),
    ("Dr. Andrés Director", "direccion@hospital.com", "DIRECCION_MEDICA"),
    ("Paula Analista", "analista@hospital.com", "ANALISTA_DATOS"),
    ("Jorge Seguridad", "seguridad@hospital.com", "OFICIAL_SEGURIDAD"),
    ("Diana Soporte TI", "ti@hospital.com", "TI"),
]
